import XCTest
import GoogleMaps
import MapKit

@testable import Runner

/// Pruebas de la lógica nativa que no depende de red ni de dispositivo.
///
/// Cubre lo que un iPhone en la mano no puede verificar de forma barata: qué
/// pasa con un reporte cuando no hay conexión, cuándo un ping colaborativo se
/// considera sismo y cuándo un rechazo del servidor merece reintentarse.
final class OfflineReportQueueTests: XCTestCase {
    private var defaults: UserDefaults!
    private var suiteName: String!

    override func setUp() {
        super.setUp()
        suiteName = "seismik.tests.\(UUID().uuidString)"
        defaults = UserDefaults(suiteName: suiteName)
    }

    override func tearDown() {
        defaults.removePersistentDomain(forName: suiteName)
        defaults = nil
        suiteName = nil
        super.tearDown()
    }

    private func makeQueue(
        maxEntries: Int = 50,
        maxAttempts: Int = 12,
        maxAge: TimeInterval = 30 * 24 * 60 * 60
    ) -> OfflineReportQueue {
        OfflineReportQueue(
            defaults: defaults,
            maxEntries: maxEntries,
            maxAttempts: maxAttempts,
            maxAge: maxAge
        )
    }

    private func report(
        _ id: String,
        kind: PendingReportKind = .felt,
        queuedAt: Date = Date(),
        attempts: Int = 0
    ) -> PendingReport {
        PendingReport(
            reportId: id,
            kind: kind,
            body: Data(#"{"report_id":"\#(id)"}"#.utf8),
            queuedAt: queuedAt,
            attempts: attempts
        )
    }

    func testQueuedReportSurvivesAppRestart() {
        makeQueue().enqueue(report("report-1"))

        let restarted = makeQueue()
        XCTAssertEqual(restarted.load().map(\.reportId), ["report-1"])
    }

    func testReenqueuingTheSameReportIdDoesNotDuplicate() {
        let queue = makeQueue()
        queue.enqueue(report("report-1"))
        queue.enqueue(report("report-1"))

        XCTAssertEqual(queue.pendingCount, 1)
    }

    func testFullQueueKeepsTheNewestReports() {
        let queue = makeQueue(maxEntries: 2)
        ["a", "b", "c"].forEach { queue.enqueue(report($0)) }

        XCTAssertEqual(queue.load().map(\.reportId), ["b", "c"])
    }

    func testFlushSendsInOrderAndEmptiesTheQueue() async {
        let queue = makeQueue()
        queue.enqueue(report("a"))
        queue.enqueue(report("b", kind: .damage))

        var sent: [String] = []
        let result = await queue.flush { pending in
            sent.append("\(pending.kind.rawValue):\(pending.reportId)")
        }

        XCTAssertEqual(sent, ["felt:a", "damage:b"])
        XCTAssertEqual(result.sent, 2)
        XCTAssertEqual(result.remaining, 0)
        XCTAssertEqual(queue.pendingCount, 0)
    }

    func testANetworkFailureStopsTheFlushAndKeepsTheRest() async {
        let queue = makeQueue()
        ["a", "b", "c"].forEach { queue.enqueue(report($0)) }

        var attempts = 0
        let result = await queue.flush { pending in
            attempts += 1
            if pending.reportId != "a" {
                throw URLError(.notConnectedToInternet)
            }
        }

        // Se detiene en «b»: reintentar «c» sólo repetiría el mismo error.
        XCTAssertEqual(attempts, 2)
        XCTAssertEqual(result.sent, 1)
        XCTAssertEqual(queue.load().map(\.reportId), ["b", "c"])
        XCTAssertEqual(queue.load().first?.attempts, 1)
    }

    func testAPermanentRejectionIsDiscardedInsteadOfRetriedForever() async {
        let queue = makeQueue()
        queue.enqueue(report("a"))
        queue.enqueue(report("b"))

        let result = await queue.flush { pending in
            if pending.reportId == "a" {
                throw PermanentReportRejection("cuerpo inválido")
            }
        }

        XCTAssertEqual(result.discarded, 1)
        XCTAssertEqual(result.sent, 1)
        XCTAssertEqual(queue.pendingCount, 0)
    }

    func testAnExpiredReportIsDroppedWithoutSending() async {
        let queue = makeQueue(maxAge: 60)
        queue.enqueue(report("viejo", queuedAt: Date().addingTimeInterval(-120)))

        var attempts = 0
        let result = await queue.flush { _ in attempts += 1 }

        XCTAssertEqual(attempts, 0)
        XCTAssertEqual(result.discarded, 1)
        XCTAssertEqual(queue.pendingCount, 0)
    }

    func testAReportThatExhaustsItsAttemptsLeavesTheQueue() async {
        let queue = makeQueue(maxAttempts: 3)
        queue.enqueue(report("a", attempts: 2))

        let result = await queue.flush { _ in throw URLError(.timedOut) }

        XCTAssertEqual(result.discarded, 1)
        XCTAssertEqual(queue.pendingCount, 0)
    }

    func testCorruptStorageIsDiscardedInsteadOfCrashing() {
        defaults.set(Data("no es json".utf8), forKey: "seismik.pending_reports")

        XCTAssertEqual(makeQueue().load().count, 0)
    }

    func testTheStoredBodyIsPreservedByteForByte() {
        // La firma HMAC cubre estos bytes: recodificar el modelo al reintentar
        // podría cambiar el orden de las claves y invalidar la firma.
        let body = Data(#"{"report_id":"x","felt":true}"#.utf8)
        let queue = makeQueue()
        queue.enqueue(PendingReport(reportId: "x", kind: .felt, body: body))

        XCTAssertEqual(makeQueue().load().first?.body, body)
    }

    func testEachKindTargetsItsOwnEndpoint() {
        XCTAssertEqual(PendingReportKind.felt.path, "v1/reports/felt")
        XCTAssertEqual(PendingReportKind.damage.path, "v1/reports/damage")
    }
}

final class SeismikDSPTests: XCTestCase {
    func testVarianceNeedsEnoughSamplesToMeanAnything() {
        XCTAssertEqual(SeismikDSP.variance(of: [0.1, 0.2, 0.3]), .infinity)
    }

    func testAQuietDeviceHasLowVariance() {
        let quiet = Array(repeating: 0.10, count: 20)
        XCTAssertLessThan(SeismikDSP.variance(of: quiet), SeismikDSP.userMotionVarianceThreshold)
    }

    func testWalkingProducesVarianceAboveTheThreshold() {
        let noisy = (0..<20).map { $0.isMultiple(of: 2) ? 0.0 : 2.0 }
        XCTAssertGreaterThan(SeismikDSP.variance(of: noisy), SeismikDSP.userMotionVarianceThreshold)
    }

    func testAStrongShakeOnAQuietDeviceIsReported() {
        XCTAssertTrue(
            SeismikDSP.shouldReport(
                magnitude: SeismikDSP.shakeThreshold + 0.1,
                previousVariance: 0.01,
                isCharging: false,
                secondsSinceLastPing: 10
            )
        )
    }

    func testMotionBelowTheThresholdIsIgnored() {
        XCTAssertFalse(
            SeismikDSP.shouldReport(
                magnitude: SeismikDSP.shakeThreshold - 0.01,
                previousVariance: 0.01,
                isCharging: false,
                secondsSinceLastPing: 10
            )
        )
    }

    func testUserMovementIsRejectedEvenWhenStrong() {
        XCTAssertFalse(
            SeismikDSP.shouldReport(
                magnitude: 5,
                previousVariance: 0.9,
                isCharging: false,
                secondsSinceLastPing: 10
            )
        )
    }

    func testChargingAllowsTwiceTheVariance() {
        let variance = SeismikDSP.userMotionVarianceThreshold * 1.5
        XCTAssertFalse(
            SeismikDSP.shouldReport(
                magnitude: 5, previousVariance: variance,
                isCharging: false, secondsSinceLastPing: 10
            )
        )
        XCTAssertTrue(
            SeismikDSP.shouldReport(
                magnitude: 5, previousVariance: variance,
                isCharging: true, secondsSinceLastPing: 10
            )
        )
    }

    func testTheCooldownPreventsAStreamOfPings() {
        XCTAssertFalse(
            SeismikDSP.shouldReport(
                magnitude: 5,
                previousVariance: 0.01,
                isCharging: false,
                secondsSinceLastPing: SeismikDSP.cooldown - 0.5
            )
        )
    }

    func testTheThresholdMatchesTheAndroidClient() {
        // 0.04 g. Si las plataformas divergen, el quorum del backend deja de
        // ser comparable entre dispositivos.
        XCTAssertEqual(SeismikDSP.shakeThreshold, 0.04 * 9.80665, accuracy: 1e-9)
    }
}

final class SeismikAPIErrorTests: XCTestCase {
    func testOnlyAccountSession401ExpiresTheAccount() {
        let account = SeismikAPIError.rejected(status: 401, message: "Account session expired")
        let device = SeismikAPIError.rejected(status: 401, message: "Device session expired")
        XCTAssertTrue(account.isAccountSessionRejected)
        XCTAssertFalse(account.isDeviceSessionRejected)
        XCTAssertFalse(device.isAccountSessionRejected)
        XCTAssertTrue(device.isDeviceSessionRejected)
        XCTAssertFalse(SeismikAPIError.rejected(status: 403, message: "Account session").isAccountSessionRejected)
        XCTAssertFalse(SeismikAPIError.accountRequired.isDeviceSessionRejected)
    }
    func testClientContractErrorsAreNotRetried() {
        XCTAssertTrue(SeismikAPIError.rejected(status: 422, message: "").isPermanent)
        XCTAssertTrue(SeismikAPIError.rejected(status: 401, message: "").isPermanent)
    }

    func testTransientStatusesStayInTheQueue() {
        XCTAssertFalse(SeismikAPIError.rejected(status: 500, message: "").isPermanent)
        XCTAssertFalse(SeismikAPIError.rejected(status: 429, message: "").isPermanent)
        XCTAssertFalse(SeismikAPIError.rejected(status: 408, message: "").isPermanent)
    }

    func testAMissingPushTokenIsWorthRetrying() {
        // APNs entrega el token unos instantes después del arranque.
        XCTAssertFalse(SeismikAPIError.pushTokenUnavailable.isPermanent)
    }
}

final class FeltAreaTests: XCTestCase {
    private func event(magnitude: Double? = 6, depth: Double? = 10, date: Date? = Date()) -> SeismicEvent {
        SeismicEvent(id: UUID().uuidString, place: "Los Santos", magnitude: magnitude,
                     depthKm: depth, latitude: 6.80, longitude: -73.10, detectedAt: date)
    }

    func testSharedIntensityVectors() {
        let vectors: [(Double, Double?, Double, Double)] = [
            (4, 150, 40, 3.066), (4, 150, 290, 1.652), (4, 10, 0, 4.567),
            (6, 10, 100, 4.242), (7, 10, 281, 4.308), (6, 55, 0, 5.367), (4.5, nil, 0, 5.275)
        ]
        for (m, depth, distance, expected) in vectors {
            XCTAssertEqual(FeltArea.intensity(magnitude: m, depthKm: depth, distanceKm: distance),
                           expected, accuracy: 0.001, "M\(m), depth \(String(describing: depth)), distance \(distance)")
        }
    }

    func testSharedRadiusVectorsAndLimits() throws {
        for (m, depth, threshold, expected) in [(4.0, 10.0, 3.0, 28.93), (4, 150, 3, 60.28),
                                                (6, 10, 6, 25.19), (7, 10, 6, 76.28)] {
            let radius = try XCTUnwrap(FeltArea.radiusKm(magnitude: m, depthKm: depth, threshold: threshold))
            XCTAssertEqual(radius, expected, accuracy: 0.01)
            XCTAssertEqual(FeltArea.intensity(magnitude: m, depthKm: depth, distanceKm: radius),
                           threshold, accuracy: 0.000001)
        }
        XCTAssertNil(FeltArea.radiusKm(magnitude: 2.5, depthKm: 10))
        XCTAssertEqual(FeltArea.radiusKm(magnitude: 8.5, depthKm: 30), 2000)
    }

    func testMonotonicityAndDepthInterpolation() {
        let depths: [Double?] = [nil, 10, 45, 150]
        for depth in depths {
            var previous = Double.infinity
            for distance in stride(from: 0.0, to: 1000, by: 5) {
                let current = FeltArea.intensity(magnitude: 6, depthKm: depth, distanceKm: distance)
                XCTAssertLessThanOrEqual(current, previous)
                previous = current
            }
        }
        for magnitude in [4.0, 5, 6, 7] {
            for boundary in [40.0, 70] {
                XCTAssertEqual(FeltArea.intensity(magnitude: magnitude, depthKm: boundary - 0.1, distanceKm: 0),
                               FeltArea.intensity(magnitude: magnitude, depthKm: boundary + 0.1, distanceKm: 0), accuracy: 0.05)
            }
        }
        XCTAssertEqual(FeltArea.intensity(magnitude: 4.5, depthKm: -1, distanceKm: 0),
                       FeltArea.intensity(magnitude: 4.5, depthKm: nil, distanceKm: 0))
    }

    func testBucaramangaNestAndNames() throws {
        let quake = event(magnitude: 4, depth: 150)
        XCTAssertGreaterThanOrEqual(try XCTUnwrap(FeltArea.localIntensity(for: quake,
            at: CLLocationCoordinate2D(latitude: 7.119, longitude: -73.123))), 3)
        XCTAssertLessThan(try XCTUnwrap(FeltArea.localIntensity(for: quake,
            at: CLLocationCoordinate2D(latitude: 4.711, longitude: -74.072))), 3)
        XCTAssertNil(FeltArea.localIntensity(for: quake, at: nil))
        XCTAssertEqual(FeltArea.roman(3.066), "III")
        XCTAssertEqual(FeltArea.roman(12.4), "XII")
        XCTAssertEqual(FeltArea.name(1), "no sentido")
        XCTAssertEqual(FeltArea.name(2.6), "débil")
        XCTAssertEqual(FeltArea.name(6.2), "fuerte")
        XCTAssertEqual(FeltArea.name(11), "extremo")
    }

    func testRingsAndRecentMapLimit() throws {
        XCTAssertEqual(FeltArea.perimeter(for: event()).map(\.intensity), [3, 4, 6])
        XCTAssertTrue(FeltArea.perimeter(for: event(magnitude: nil)).isEmpty)
        XCTAssertTrue(FeltArea.perimeter(for: event(magnitude: 2.5)).isEmpty)
        let now = Date(timeIntervalSince1970: 1_800_000_000)
        let fresh = event(date: now.addingTimeInterval(-7200))
        let old = event(date: now.addingTimeInterval(-5 * 86400))
        XCTAssertEqual(FeltArea.recentEvents([fresh, old, event(magnitude: 2.5, date: now)], now: now).map(\.id), [fresh.id])
        XCTAssertEqual(FeltArea.recentEvents((0..<35).map { _ in event(date: now) }, now: now).count, 30)
        let ring = try XCTUnwrap(FeltArea.perimeter(for: fresh).first)
        let circle = FeltArea.circle(ring, center: try XCTUnwrap(fresh.coordinate))
        XCTAssertEqual(circle.radius, 256.92 * 1000, accuracy: 10)
        XCTAssertNil(FeltArea.renderer(for: circle).lineDashPattern)
        XCTAssertGreaterThan(circle.boundingMapRect.width, 0)
    }
}

final class NativeNotificationPolicyTests: XCTestCase {
    func testCriticalOfficialIsNotSelectedByMagnitude() throws {
        let payload: [AnyHashable: Any] = ["event_id": "official", "type": "official_report_update",
            "critical": "true", "magnitude": "3.9", "origin_time": "2026-09-13T18:00:00Z"]
        let event = try XCTUnwrap(SeismicEvent(notificationUserInfo: payload))
        XCTAssertTrue(event.isCriticalOfficial)
        XCTAssertTrue(SeismikNotificationPresenter.shouldPresentAlarm(for: event))
        XCTAssertEqual(SeismikNotificationPresenter.alertTitle(for: event), "SISMO FUERTE EN TU ZONA")
        XCTAssertEqual(SeismikNotificationPresenter.alertInstruction(for: event), "Revisa a tu familia y prepárate para réplicas")
        XCTAssertEqual(SeismikNotificationPresenter.elapsedDescription(for: event, now: try XCTUnwrap(event.detectedAt).addingTimeInterval(120)),
                       "Hace 2 min · desde el sismo")
        var advisory = payload
        advisory["critical"] = "false"
        advisory["magnitude"] = "8.5"
        XCTAssertFalse(SeismikNotificationPresenter.shouldPresentAlarm(for: try XCTUnwrap(SeismicEvent(notificationUserInfo: advisory))))
        XCTAssertEqual(try JSONDecoder().decode(SeismicEvent.self, from: JSONEncoder().encode(event)), event)
    }

    func testEarlyCandidateKeepsItsCopyAndFamilyIsNotAQuake() throws {
        let candidate = try XCTUnwrap(SeismicEvent(notificationUserInfo: ["event_id": "early", "type": "earthquake_candidate"]))
        XCTAssertTrue(SeismikNotificationPresenter.shouldPresentAlarm(for: candidate))
        XCTAssertEqual(SeismikNotificationPresenter.alertTitle(for: candidate), "ALERTA SÍSMICA")
        XCTAssertEqual(SeismikNotificationPresenter.alertInstruction(for: candidate), "PROTÉGETE AHORA")
        XCTAssertNil(SeismicEvent(notificationUserInfo: ["type": "family_status"]))
    }
}

/// All requests terminate in this URLProtocol; these tests never contact Seismik.
private final class FamilyStubProtocol: URLProtocol {
    static var handler: ((URLRequest) throws -> (Int, String))?
    override class func canInit(with request: URLRequest) -> Bool { true }
    override class func canonicalRequest(for request: URLRequest) -> URLRequest { request }
    override func startLoading() {
        do {
            guard let handler = Self.handler else { throw URLError(.badServerResponse) }
            let (status, body) = try handler(request)
            let response = HTTPURLResponse(url: request.url!, statusCode: status,
                httpVersion: nil, headerFields: ["Content-Type": "application/json"])!
            client?.urlProtocol(self, didReceive: response, cacheStoragePolicy: .notAllowed)
            client?.urlProtocol(self, didLoad: Data(body.utf8))
            client?.urlProtocolDidFinishLoading(self)
        } catch { client?.urlProtocol(self, didFailWithError: error) }
    }
    override func stopLoading() {}

    static func body(_ request: URLRequest) throws -> [String: Any] {
        var data = request.httpBody ?? Data()
        if data.isEmpty, let stream = request.httpBodyStream {
            stream.open()
            defer { stream.close() }
            var buffer = [UInt8](repeating: 0, count: 1024)
            while true {
                let count = stream.read(&buffer, maxLength: buffer.count)
                if count <= 0 { break }
                data.append(contentsOf: buffer.prefix(count))
            }
        }
        return try XCTUnwrap(JSONSerialization.jsonObject(with: data) as? [String: Any])
    }
}

final class NativeFamilyContractTests: XCTestCase {
    private var store: KeychainStore!
    private var api: SeismikAPIClient!
    private var session: URLSession!

    override func setUpWithError() throws {
        // CI runs unsigned on the simulator: the real Keychain answers -34018
        // (missing entitlement). The fixtures live in memory instead.
        store = KeychainStore.inMemory()
        try store.set("test-account", for: "seismik.account_session_token")
        try store.set("test-device-old", for: "seismik.device_session_token")
        let config = URLSessionConfiguration.ephemeral
        config.protocolClasses = [FamilyStubProtocol.self]
        session = URLSession(configuration: config)
        api = SeismikAPIClient(baseURL: URL(string: "https://family-tests.invalid")!, session: session, keychain: store)
    }

    override func tearDownWithError() throws {
        FamilyStubProtocol.handler = nil
        // If setUp failed these are nil; unwrapping them crashed the test host.
        session?.invalidateAndCancel()
        try store?.remove("seismik.account_session_token")
        try store?.remove("seismik.device_session_token")
    }

    func testCreateAndJoinMatchAndroidContract() async throws {
        FamilyStubProtocol.handler = { request in
            XCTAssertEqual(request.httpMethod, "POST")
            XCTAssertEqual(request.value(forHTTPHeaderField: "X-Seismik-Account-Session"), "test-account")
            let body = try FamilyStubProtocol.body(request)
            XCTAssertEqual(body["display_name"] as? String, "Ana")
            if request.url?.path == "/v1/family/circle" {
                XCTAssertEqual(body["circle_name"] as? String, "Mi familia")
            } else {
                XCTAssertEqual(request.url?.path, "/v1/family/join")
                XCTAssertEqual(body["invite_code"] as? String, "INVITE-123")
            }
            return (200, "{}")
        }
        try await api.createFamilyCircle(displayName: " Ana ", circleName: " Mi familia ")
        try await api.joinFamilyCircle(inviteCode: " INVITE-123 ", displayName: " Ana ")
    }

    func testRotatedDeviceSessionRetriesWithoutExpiringAccount() async throws {
        let store = try XCTUnwrap(store)
        var attempts = 0
        FamilyStubProtocol.handler = { request in
            attempts += 1
            if attempts == 1 {
                XCTAssertEqual(request.value(forHTTPHeaderField: "X-Seismik-Device-Session"), "test-device-old")
                try store.set("test-device-new", for: "seismik.device_session_token")
                return (401, "Device session expired")
            }
            XCTAssertEqual(request.value(forHTTPHeaderField: "X-Seismik-Device-Session"), "test-device-new")
            return (200, "{\"circle_id\":\"circle-1\",\"circle_name\":\"Familia\",\"members\":[]}")
        }
        let circle = try await api.fetchFamilyCircle()
        XCTAssertEqual(circle?.circleId, "circle-1")
        XCTAssertEqual(attempts, 2)
        XCTAssertEqual(api.accountSessionToken, "test-account")
    }

    func testAccount401IsNotRetriedAndDevice401RemainsDistinct() async throws {
        for message in ["Account session expired", "Device session expired"] {
            var attempts = 0
            FamilyStubProtocol.handler = { _ in
                attempts += 1
                return (401, message)
            }
            do {
                _ = try await api.fetchFamilyCircle()
                XCTFail("Expected rejected session")
            } catch let error as SeismikAPIError {
                XCTAssertEqual(error.isAccountSessionRejected, message.contains("Account session"))
                XCTAssertEqual(error.isDeviceSessionRejected, !message.contains("Account session"))
            }
            XCTAssertEqual(attempts, 1)
            XCTAssertEqual(api.accountSessionToken, "test-account")
        }
    }

    func testAssociationRequiresRegisteredDevice() async throws {
        try store.remove("seismik.device_session_token")
        FamilyStubProtocol.handler = { _ in XCTFail("Must not associate before registration"); return (200, "{}") }
        do {
            try await api.linkDeviceToAccount()
            XCTFail("Expected missing device session")
        } catch let error as SeismikAPIError {
            XCTAssertTrue(error.isDeviceSessionRejected)
        }
        try store.set("test-device-registered", for: "seismik.device_session_token")
        FamilyStubProtocol.handler = { request in
            XCTAssertEqual(request.url?.path, "/v1/account/device")
            XCTAssertEqual(request.httpMethod, "POST")
            XCTAssertEqual(request.value(forHTTPHeaderField: "X-Seismik-Device-Session"), "test-device-registered")
            return (200, "{}")
        }
        try await api.linkDeviceToAccount()
    }

    func testFamilyCheckInKeepsConsentAndWorksWithoutLocation() async throws {
        FamilyStubProtocol.handler = { request in
            XCTAssertEqual(request.url?.path, "/v1/family/status")
            XCTAssertEqual(request.httpMethod, "PUT")
            let body = try FamilyStubProtocol.body(request)
            XCTAssertEqual(body["event_id"] as? String, "quake-1")
            XCTAssertEqual(body["share_minutes"] as? Int, 240)
            if body["status"] as? String == "safe" {
                XCTAssertNil(body["location"])
            } else {
                XCTAssertEqual(body["status"] as? String, "need_help")
                let location = try XCTUnwrap(body["location"] as? [String: Any])
                XCTAssertEqual(location["precision"] as? String, "approximate")
                XCTAssertEqual(location["precise_location_consent"] as? Bool, false)
            }
            return (200, "{}")
        }
        try await api.reportFamilyStatus(needsHelp: false, eventId: "quake-1", latitude: nil, longitude: nil, precise: false)
        try await api.reportFamilyStatus(needsHelp: true, eventId: "quake-1", latitude: 4.65, longitude: -74.05, precise: false)
    }

    /// El host de pruebas no configura Firebase, igual que un iPhone sin
    /// DeviceCheck: antes el registro ni siquiera llegaba al servidor.
    func testRegistrationWithoutAppCheckStillReachesTheServer() async throws {
        FamilyStubProtocol.handler = { request in
            XCTAssertEqual(request.url?.path, "/v1/devices/register")
            let body = try FamilyStubProtocol.body(request)
            XCTAssertEqual(body["platform"] as? String, "ios")
            XCTAssertEqual(body["app_attest_token"] as? String, SeismikAPIClient.unverifiedIntegrityMarker)
            return (200, "{\"device_id\":\"device-1\",\"registered\":true,\"crowd_token\":\"crowd-new\",\"device_session_token\":\"test-device-registered\"}")
        }
        let registered = try await api.registerDevice(latitude: 4.65, longitude: -74.05)
        XCTAssertTrue(registered)
        XCTAssertEqual(api.deviceSessionToken, "test-device-registered")
    }

    func testRegistrationProblemsAreExplainedWithoutSystemJargon() {
        let errors: [SeismikAPIError] = [
            .rejected(status: 401, message: "Device integrity verification failed"),
            .rejected(status: 503, message: "Firebase App Check aún no está disponible"),
            .malformedResponse,
        ]
        for error in errors {
            XCTAssertFalse(error.registrationMessage.contains("Firebase"))
            XCTAssertFalse(error.registrationMessage.contains("401"))
            XCTAssertFalse(error.registrationMessage.contains("503"))
        }
    }

    /// Desde el 11 de septiembre el .xcconfig entregaba `https:`: `//` es un
    /// comentario allí. Ninguna petición salía del iPhone.
    @MainActor
    func testTheAPIBaseURLSurvivesXcconfigCommentTruncation() {
        let production = URL(string: "https://api.seismik.org")!
        XCTAssertEqual(SeismikAPIClient.resolveBaseURL(configured: "https:"), production)
        XCTAssertEqual(SeismikAPIClient.resolveBaseURL(configured: "$(SEISMIK_API_BASE_URL)"), production)
        XCTAssertEqual(SeismikAPIClient.resolveBaseURL(configured: ""), production)
        XCTAssertEqual(SeismikAPIClient.resolveBaseURL(configured: nil), production)
        XCTAssertEqual(SeismikAPIClient.resolveBaseURL(configured: "http://api.seismik.org"), production)
        XCTAssertEqual(
            SeismikAPIClient.resolveBaseURL(configured: " https://staging.seismik.org "),
            URL(string: "https://staging.seismik.org")!
        )
    }

    func testAFailedHistoryDownloadIsReportedInsteadOfShownAsFresh() async throws {
        FamilyStubProtocol.handler = { request in
            XCTAssertEqual(request.url?.path, "/v1/events/history")
            return (500, "{\"detail\":\"catálogo caído\"}")
        }
        do {
            _ = try await api.fetchRecentEvents()
            XCTFail("A failed download must not return the cached list as fresh")
        } catch let error as SeismikAPIError {
            guard case let .rejected(status, _) = error else { return XCTFail("Unexpected \(error)") }
            XCTAssertEqual(status, 500)
        }
    }

    func testTheHistoryReturnsWhatTheServerSent() async throws {
        FamilyStubProtocol.handler = { _ in
            (200, "{\"events\":[{\"event_id\":\"usgs_global:us1\",\"type\":\"official_report_update\",\"origin_time\":\"2026-09-15T02:56:51Z\",\"latitude\":4.6,\"longitude\":-74.0,\"magnitude\":3.1}]}")
        }
        let fresh = try await api.fetchRecentEvents()
        XCTAssertEqual(fresh.map(\.id), ["usgs_global:us1"])

        FamilyStubProtocol.handler = { _ in (200, "{\"events\":[]}") }
        let empty = try await api.fetchRecentEvents()
        XCTAssertTrue(empty.isEmpty, "An empty answer must not bring back the previous list")
    }
}

/// El ajuste de mapas sólo ofrece Apple y Google, y Google sólo se dibuja si el
/// build trajo la clave del SDK: sin ella el mapa saldría gris.
final class MapProviderChoiceTests: XCTestCase {
    private func event(magnitude: Double?, isPreliminary: Bool = false) -> SeismicEvent {
        SeismicEvent(id: UUID().uuidString, place: "Los Santos", magnitude: magnitude,
                     depthKm: 10, latitude: 6.80, longitude: -73.10, detectedAt: Date(),
                     isPreliminary: isPreliminary)
    }

    func testTheOnlyProvidersAreAppleAndGoogle() {
        XCTAssertEqual(MapProviderChoice.allCases.map(\.rawValue), ["apple", "google"])
        XCTAssertEqual(MapProviderChoice.apple.label, "Apple Maps")
        XCTAssertEqual(MapProviderChoice.google.label, "Google Maps")
    }

    func testOldPreferencesFallBackToAppleMaps() {
        // Quien venga del build anterior tiene guardado "osm" o "system".
        XCTAssertEqual(MapProviderChoice.stored("osm"), .apple)
        XCTAssertEqual(MapProviderChoice.stored("system"), .apple)
        XCTAssertEqual(MapProviderChoice.stored(""), .apple)
        XCTAssertEqual(MapProviderChoice.stored("google"), .google)
        XCTAssertEqual(MapProviderChoice.stored("apple"), .apple)
    }

    func testGoogleIsOnlyDrawnWhenTheBuildHasItsKey() {
        XCTAssertEqual(MapProviderChoice.resolved(stored: "google", googleIsReady: true), .google)
        XCTAssertEqual(
            MapProviderChoice.resolved(stored: "google", googleIsReady: false), .apple,
            "Sin clave, Google Maps dibuja una cuadrícula gris: es peor que Apple Maps"
        )
        XCTAssertEqual(MapProviderChoice.resolved(stored: "apple", googleIsReady: true), .apple)
    }

    func testEveryEarthquakeGetsItsOwnBadgeDrawnForGoogleMarkers() {
        // Google pinta imágenes, no vistas: si el dibujo saliera vacío, el mapa
        // se quedaría sin sismos y nadie vería el fallo hasta el teléfono.
        for event in [event(magnitude: 6.2), event(magnitude: 2.4), event(magnitude: nil, isPreliminary: true)] {
            XCTAssertEqual(GoogleMarkerIcon.magnitude(for: event).size, CGSize(width: 48, height: 32))
        }
        XCTAssertEqual(GoogleMarkerIcon.station.size, CGSize(width: 12, height: 12))
    }

    func testTheGoogleRingsKeepTheColoursOfTheAppleOnes() throws {
        let quake = event(magnitude: 6)
        let ring = try XCTUnwrap(FeltArea.perimeter(for: quake).first)
        let center = try XCTUnwrap(quake.coordinate)
        let google = GoogleMarkerIcon.circle(ring, center: center)
        let apple = FeltArea.renderer(for: FeltArea.circle(ring, center: center))

        XCTAssertEqual(google.radius, ring.radiusKm * 1_000, accuracy: 1)
        XCTAssertEqual(google.strokeColor, apple.strokeColor)
        XCTAssertEqual(google.fillColor, apple.fillColor)
    }

    func testTheGoogleFrameCoversTheWholeFeltRadius() {
        let bogota = CLLocationCoordinate2D(latitude: 4.65, longitude: -74.05)
        let frame = GoogleMarkerIcon.bounds(around: bogota, radiusKm: 120)

        XCTAssertTrue(frame.isValid)
        // Un punto a ~100 km al norte entra en el encuadre; uno a ~400 km, no.
        XCTAssertTrue(frame.contains(CLLocationCoordinate2D(latitude: 5.55, longitude: -74.05)))
        XCTAssertFalse(frame.contains(CLLocationCoordinate2D(latitude: 8.25, longitude: -74.05)))
    }
}
