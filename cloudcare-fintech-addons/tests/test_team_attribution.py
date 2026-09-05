from __future__ import annotations

from team_attribution import TaggedResourceSample, aggregate_by_team


def _sample(resource_id, cost, tags=None, environment=None, resource_type="ec2"):
    return TaggedResourceSample(
        resource_id=resource_id,
        resource_type=resource_type,
        environment=environment,
        monthly_cost=cost,
        tags=tags or {},
    )


def test_aggregate_groups_by_tag_value():
    resources = [
        _sample("i-1", 100.0, tags={"team": "payments"}, environment="prod"),
        _sample("i-2", 50.0, tags={"team": "payments"}, environment="staging"),
        _sample("i-3", 30.0, tags={"team": "risk"}, environment="prod"),
    ]
    report = aggregate_by_team(resources)

    assert report.teams[0].team == "payments"
    assert report.teams[0].total_monthly_cost == 150.0
    assert report.teams[0].resource_count == 2
    assert sorted(report.teams[0].environments) == ["prod", "staging"]
    assert report.teams[1].team == "risk"
    assert report.untagged_resources == []


def test_aggregate_is_case_insensitive_on_tag_key():
    resources = [_sample("i-1", 100.0, tags={"Team": "payments"})]
    report = aggregate_by_team(resources, tag_key="team")
    assert report.teams[0].team == "payments"


def test_aggregate_treats_blank_tag_value_as_untagged():
    resources = [_sample("i-1", 100.0, tags={"team": "   "})]
    report = aggregate_by_team(resources)
    assert report.teams == []
    assert len(report.untagged_resources) == 1


def test_aggregate_sorts_teams_by_cost_descending():
    resources = [
        _sample("i-1", 10.0, tags={"team": "small"}),
        _sample("i-2", 500.0, tags={"team": "big"}),
        _sample("i-3", 100.0, tags={"team": "medium"}),
    ]
    report = aggregate_by_team(resources)
    assert [t.team for t in report.teams] == ["big", "medium", "small"]


def test_aggregate_tracks_untagged_resources_and_cost_separately():
    resources = [
        _sample("i-1", 100.0, tags={"team": "payments"}),
        _sample("i-2", 40.0, tags={}),
        _sample("i-3", 60.0, tags={"owner": "someone"}),  # wrong key for "team"
    ]
    report = aggregate_by_team(resources, tag_key="team")

    assert report.untagged_cost == 100.0
    assert len(report.untagged_resources) == 2
    assert report.total_cost == 200.0
    assert report.untagged_pct == 50.0


def test_aggregate_handles_empty_resource_list():
    report = aggregate_by_team([])
    assert report.teams == []
    assert report.untagged_resources == []
    assert report.total_cost == 0.0
    assert report.untagged_pct == 0.0  # must not divide by zero
