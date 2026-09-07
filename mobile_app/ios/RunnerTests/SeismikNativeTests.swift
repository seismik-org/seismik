import XCTest

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
