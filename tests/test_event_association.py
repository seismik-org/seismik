from api.event_association import associate_events


def event(source, suffix="1", seconds=0, latitude=4.6, magnitude=4.0, depth=10):
    return dict(
        event_id=f"{source}:{suffix}",
        source_id=source,
        type="official_report_update",
        origin_time=f"2026-10-12T12:00:{seconds:02d}Z",
        latitude=latitude,
        longitude=-74.0,
        depth_km=depth,
        magnitude=magnitude,
        magnitude_type="Mw",
        official_url=f"https://{source}.example/event/{suffix}",
    )


def test_different_magnitudes_scales_preserved_order_independent():
    a, b, c = (
        event("sgc_colombia", magnitude=4.2),
        event("usgs_global", seconds=8, magnitude=4.8),
        event("emsc_global", seconds=12),
    )
    b["magnitude_type"] = "mb"
    grouped = associate_events([c, b, a])
    assert grouped == associate_events([a, b, c])
    assert len(grouped) == 1
    assert grouped[0]["event_id"] == a["event_id"]
    assert grouped[0]["magnitude"] == 4.2
    assert [r["magnitude"] for r in grouped[0]["source_reports"]] == [4.2, 4.8, 4.0]
    assert grouped[0]["source_reports"][1]["magnitude_type"] == "mb"
    assert grouped[0]["source_reports"][1]["official_url"] == b["official_url"]


def test_ambiguous_aftershocks_and_transitive_chain_remain_separate():
    assert (
        len(
            associate_events(
                [
                    event("sgc_colombia"),
                    event("sgc_colombia", "2", seconds=20),
                    event("usgs_global", seconds=10),
                ]
            )
        )
        == 3
    )
    assert (
        len(
            associate_events(
                [event("a", latitude=4.6), event("b", latitude=4.9), event("c", latitude=5.2)]
            )
        )
        == 3
    )


def test_far_missing_depth_time_preliminary_and_same_source_not_associated():
    for other in (
        event("b", latitude=6),
        event("b", depth=150),
        event("b", seconds=59),
        event("a", "2"),
    ):
        assert len(associate_events([event("a"), other])) == 2
    for field, value in (
        ("latitude", None),
        ("origin_time", "bad"),
        ("preliminary", True),
        ("type", "earthquake_candidate"),
    ):
        other = event("b")
        other[field] = value
        assert len(associate_events([event("a"), other])) == 2


def test_revisions_replace_only_same_id_and_inputs_are_not_mutated():
    old, new = event("a"), event("a", magnitude=5)
    old["updated_at"] = "2026-10-12T12:01:00Z"
    new["updated_at"] = "2026-10-12T12:02:00Z"
    result = associate_events([new, old])
    assert len(result) == 1 and result[0]["magnitude"] == 5
    assert "source_reports" not in new
