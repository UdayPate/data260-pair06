"""
Events: posting, search, eligibility, registration and the company's registration view.
Run from backend/:   python -m pytest -q
"""
from datetime import date, datetime, timedelta, timezone

import pytest

from app import models

NOW = datetime.now()


def when(days: int, hour: int = 10) -> str:
    """ISO date-time `days` from today at `hour`:00 (e.g. '2026-11-05T10:00:00')."""
    return (NOW + timedelta(days=days)).replace(hour=hour, minute=0, second=0, microsecond=0).isoformat()


def day(days: int) -> str:
    return (NOW + timedelta(days=days)).date().isoformat()


def bearer(token):
    return {"Authorization": f"Bearer {token}"}


def signup(client, role, name, email, **extra):
    body = {"name": name, "email": email, "password": "Secret123"}
    body.update({"company": {"location": "San Jose"}, "student": {"college": "SJSU"}}[role])
    body.update(extra)
    r = client.post(f"/auth/{role}/signup", json=body)
    assert r.status_code == 201, r.text
    return bearer(r.json()["access_token"]), r.json()["user_id"]


def event_body(**overrides):
    body = {"name": "Career Fair", "description": "Meet recruiters from local companies.",
            "event_datetime": when(10), "location": "123 Main St", "city": "San Jose",
            "eligible_majors": ["All"]}
    body.update(overrides)
    return body


@pytest.fixture()
def world(client, db):
    """Companies Acme and Globex; students Ada (Computer Science), Bob (Marketing), Cara (no major).
    Acme posts E1-E4 through the API; a past event is inserted directly."""
    acme, acme_id = signup(client, "company", "Acme Corp", "hr@acme.com")
    globex, globex_id = signup(client, "company", "Globex Inc", "hr@globex.com")
    ada, ada_id = signup(client, "student", "Ada Lovelace", "ada@example.com")
    bob, bob_id = signup(client, "student", "Bob Builder", "bob@example.com")
    cara, cara_id = signup(client, "student", "Cara Cole", "cara@example.com")
    client.patch("/students/me", headers=ada, json={"major": "Computer Science", "skills": ["Python"]})
    client.patch("/students/me", headers=bob, json={"major": "Marketing"})

    def post(headers, **kw):
        r = client.post("/events", json=event_body(**kw), headers=headers)
        assert r.status_code == 201, r.text
        return r.json()["id"]

    ids = {
        "tech": post(acme, name="Tech Career Fair", city="San Jose", event_datetime=when(10),
                     eligible_majors=["Computer Science", "Data Science"]),
        "mixer": post(acme, name="Marketing Mixer", city="Sunnyvale", event_datetime=when(5, 18),
                      eligible_majors=["Marketing"]),
        "open": post(globex, name="Open House", city="Mountain View", event_datetime=when(20), eligible_majors=["All"]),
        "workshop": post(acme, name="Resume Workshop", city="San Jose", event_datetime=when(40), eligible_majors=["All"]),
    }
    old = models.Event(company_id=acme_id, name="Old Meetup", description="This meetup already happened.",
                       event_datetime=NOW - timedelta(days=3), location="1 Old Rd", city="San Jose")
    old.eligible_majors = [models.EventEligibleMajor(major="All")]
    db.add(old)
    db.commit()
    ids["old"] = old.id
    return {"ids": ids, "acme": acme, "globex": globex, "ada": ada, "bob": bob, "cara": cara,
            "acme_id": acme_id, "ada_id": ada_id, "bob_id": bob_id, "cara_id": cara_id}


def names(response):
    assert response.status_code == 200, response.text
    return [e["name"] for e in response.json()["items"]]


def search(client, who, **params):
    return client.get("/events", params=params, headers=who)


# ===================================================================== create
def test_company_posts_event(client, company_headers):
    r = client.post("/events", json=event_body(eligible_majors=["computer science", "DATA SCIENCE"]),
                    headers=company_headers)
    assert r.status_code == 201
    e = r.json()
    assert e["name"] == "Career Fair" and e["eligible_majors"] == ["Computer Science", "Data Science"]
    assert e["company"]["name"] == "Acme Corp" and "email" not in e["company"]
    assert e["registration_count"] == 0 and e["is_past"] is False
    assert e["eligible"] is None and e["can_register"] is None       # only students get these flags


def test_majors_default_to_all_and_all_wins(client, company_headers):
    body = event_body()
    del body["eligible_majors"]
    assert client.post("/events", json=body, headers=company_headers).json()["eligible_majors"] == ["All"]
    mixed = client.post("/events", json=event_body(eligible_majors=["Marketing", "all"]), headers=company_headers)
    assert mixed.json()["eligible_majors"] == ["All"]
    dupes = client.post("/events", json=event_body(eligible_majors=["Marketing", "marketing", " MARKETING "]),
                        headers=company_headers)
    assert dupes.json()["eligible_majors"] == ["Marketing"]


def test_event_time_with_timezone_is_converted_not_rejected(client, company_headers):
    future_utc = (datetime.now(timezone.utc) + timedelta(days=5)).strftime("%Y-%m-%dT%H:%M:%SZ")
    r = client.post("/events", json=event_body(event_datetime=future_utc), headers=company_headers)
    assert r.status_code == 201 and not r.json()["event_datetime"].endswith("Z")


def test_only_companies_can_post_events(client, student_headers):
    assert client.post("/events", json=event_body()).status_code == 401
    assert client.post("/events", json=event_body(), headers=student_headers).status_code == 403


@pytest.mark.parametrize("override", [
    {"event_datetime": when(-1)}, {"event_datetime": when(-30)},          # in the past
    {"event_datetime": when(900)},                                         # too far ahead
    {"event_datetime": "next friday"}, {"event_datetime": ""},
    {"name": ""}, {"name": "x" * 201}, {"description": "short"}, {"location": "  "}, {"city": ""},
    {"eligible_majors": []}, {"eligible_majors": ["<script>"]}, {"eligible_majors": [f"Major{i}" for i in range(11)]},
    {"eligible_majors": "Marketing"}, {"eligible_majors": [5]},
    {"company_id": 2}, {"id": 9}, {"registration_count": 100},            # fields the client may not set
], ids=["yesterday", "month-ago", "3-years", "words", "blank-date", "blank-name", "long-name", "short-desc",
        "blank-location", "blank-city", "no-majors", "script-major", "11-majors", "string-majors", "number-major",
        "company-id", "id", "count"])
def test_invalid_event_rejected(client, company_headers, override):
    assert client.post("/events", json=event_body(**override), headers=company_headers).status_code == 422


def test_missing_fields_rejected(client, company_headers):
    assert client.post("/events", json={"name": "Only a name"}, headers=company_headers).status_code == 422


# ===================================================================== my events / edit
def test_mine_lists_only_own_events_with_counts(client, world):
    client.post(f"/events/{world['ids']['tech']}/register", headers=world["ada"])
    r = client.get("/events/mine", headers=world["acme"])
    assert r.status_code == 200
    got = {e["name"]: e["registration_count"] for e in r.json()["items"]}
    assert got == {"Old Meetup": 0, "Marketing Mixer": 0, "Tech Career Fair": 1, "Resume Workshop": 0}
    upcoming = client.get("/events/mine", params={"include_past": False}, headers=world["acme"])
    assert "Old Meetup" not in names(upcoming)
    assert client.get("/events/mine", headers=world["globex"]).json()["total"] == 1


def test_mine_requires_company(client, student_headers):
    assert client.get("/events/mine").status_code == 401
    assert client.get("/events/mine", headers=student_headers).status_code == 403


def test_owner_edits_event(client, world):
    eid = world["ids"]["tech"]
    r = client.patch(f"/events/{eid}", headers=world["acme"], json={
        "name": "Big Tech Fair", "location": "Convention Center", "eligible_majors": ["data science", "Mathematics"],
        "event_datetime": when(12, 14)})
    assert r.status_code == 200
    e = r.json()
    assert e["name"] == "Big Tech Fair" and e["location"] == "Convention Center"
    assert e["eligible_majors"] == ["Data Science", "Mathematics"] and e["event_datetime"].startswith(day(12))
    assert e["city"] == "San Jose"                                          # untouched fields stay
    # re-sending the same majors must not trip the UNIQUE (event, major) rule
    assert client.patch(f"/events/{eid}", headers=world["acme"],
                        json={"eligible_majors": ["Data Science", "mathematics"]}).status_code == 200


def test_changing_majors_keeps_existing_registrations(client, world):
    eid = world["ids"]["tech"]
    assert client.post(f"/events/{eid}/register", headers=world["ada"]).status_code == 201
    client.patch(f"/events/{eid}", headers=world["acme"], json={"eligible_majors": ["Marketing"]})
    assert client.get(f"/events/{eid}/registrations", headers=world["acme"]).json()["total"] == 1


def test_past_event_text_can_be_fixed_but_not_rescheduled_into_the_past(client, world):
    old = world["ids"]["old"]
    assert client.patch(f"/events/{old}", headers=world["acme"], json={"description": "A corrected description."}).status_code == 200
    assert client.patch(f"/events/{old}", headers=world["acme"], json={"event_datetime": when(-1)}).status_code == 422


def test_cannot_edit_someone_elses_event_or_a_missing_one(client, world):
    eid = world["ids"]["tech"]
    assert client.patch(f"/events/{eid}", headers=world["globex"], json={"name": "Hijacked"}).status_code == 403
    assert client.patch(f"/events/{eid}", headers=world["ada"], json={"name": "Hijacked"}).status_code == 403
    assert client.patch(f"/events/{eid}", json={"name": "Hijacked"}).status_code == 401
    assert client.patch("/events/99999", headers=world["acme"], json={"name": "X"}).status_code == 404
    assert client.get(f"/events/{eid}", headers=world["ada"]).json()["name"] == "Tech Career Fair"


@pytest.mark.parametrize("payload", [
    {"event_datetime": when(-2)}, {"name": None}, {"name": ""}, {"event_datetime": None}, {"eligible_majors": []},
    {"eligible_majors": None}, {"description": None}, {"city": None}, {"company_id": 2}, {"registration_count": 5},
], ids=["past", "null-name", "blank-name", "null-date", "no-majors", "null-majors", "null-desc", "null-city",
        "company-id", "count"])
def test_invalid_edits_rejected_and_change_nothing(client, world, payload):
    eid = world["ids"]["tech"]
    assert client.patch(f"/events/{eid}", headers=world["acme"], json=payload).status_code == 422
    e = client.get(f"/events/{eid}", headers=world["acme"]).json()
    assert e["name"] == "Tech Career Fair" and e["eligible_majors"] == ["Computer Science", "Data Science"]


# ===================================================================== search
def test_search_requires_login(client):
    assert client.get("/events").status_code == 401


def test_default_search_is_upcoming_only_in_increasing_date_order(client, world):
    got = names(search(client, world["ada"]))
    assert got == ["Marketing Mixer", "Tech Career Fair", "Open House", "Resume Workshop"]   # +5, +10, +20, +40 days
    assert "Old Meetup" not in got
    assert names(search(client, world["ada"], include_past=True))[0] == "Old Meetup"          # past ones come first
    assert client.get("/events", headers=world["acme"]).json()["total"] == 4                  # companies can browse too


def test_search_by_name_words(client, world):
    assert names(search(client, world["ada"], q="career")) == ["Tech Career Fair"]
    assert names(search(client, world["ada"], q="MARKETING mixer")) == ["Marketing Mixer"]
    assert names(search(client, world["ada"], q="fair tech")) == ["Tech Career Fair"]          # every word, any order
    assert search(client, world["ada"], q="hackathon").json()["total"] == 0
    assert search(client, world["ada"], q="%").json()["total"] == 0                            # % is not a wildcard
    assert search(client, world["ada"], q="_").json()["total"] == 0


def test_search_by_city(client, world):
    assert names(search(client, world["ada"], city="san jose")) == ["Tech Career Fair", "Resume Workshop"]
    many = client.get("/events", params=[("city", "Sunnyvale"), ("city", "Mountain View")], headers=world["ada"])
    assert names(many) == ["Marketing Mixer", "Open House"]


def test_search_by_date_range_covers_whole_days(client, world):
    assert names(search(client, world["ada"], date_from=day(10), date_to=day(20))) == ["Tech Career Fair", "Open House"]
    assert names(search(client, world["ada"], date_from=day(10), date_to=day(10))) == ["Tech Career Fair"]   # 10:00 is inside day 10
    assert names(search(client, world["ada"], date_from=day(5), date_to=day(5))) == ["Marketing Mixer"]      # 18:00 is inside day 5
    assert names(search(client, world["ada"], date_from=day(30))) == ["Resume Workshop"]
    assert names(search(client, world["ada"], date_to=day(7))) == ["Marketing Mixer"]
    assert search(client, world["ada"], date_from=day(100)).json()["total"] == 0


def test_search_by_major_returns_events_open_to_that_major_or_to_all(client, world):
    assert names(search(client, world["ada"], major="Computer Science")) == ["Tech Career Fair", "Open House", "Resume Workshop"]
    assert names(search(client, world["ada"], major="computer science")) == ["Tech Career Fair", "Open House", "Resume Workshop"]
    assert names(search(client, world["ada"], major="Marketing")) == ["Marketing Mixer", "Open House", "Resume Workshop"]
    assert names(search(client, world["ada"], major="Nursing")) == ["Open House", "Resume Workshop"]       # only the "All" events


def test_filters_combine_with_and(client, world):
    r = search(client, world["ada"], major="Computer Science", city="San Jose", date_from=day(1), date_to=day(15))
    assert names(r) == ["Tech Career Fair"]
    assert search(client, world["ada"], q="mixer", city="San Jose").json()["total"] == 0


def test_search_pagination(client, world):
    first = search(client, world["ada"], page_size=3).json()
    assert first["total"] == 4 and first["total_pages"] == 2 and len(first["items"]) == 3
    assert [e["name"] for e in search(client, world["ada"], page_size=3, page=2).json()["items"]] == ["Resume Workshop"]
    assert search(client, world["ada"], page=9).json()["items"] == []


@pytest.mark.parametrize("params", [
    {"date_from": "soon"}, {"date_to": "2026-13-45"}, {"page": 0}, {"page_size": 101}, {"include_past": "maybe"}, {"q": "x" * 101},
], ids=["bad-from", "bad-to", "page-0", "size-101", "bad-bool", "long-q"])
def test_bad_search_parameters_rejected(client, world, params):
    assert search(client, world["ada"], **params).status_code == 422


def test_student_sees_eligibility_and_registration_flags(client, world):
    client.post(f"/events/{world['ids']['open']}/register", headers=world["ada"])
    by_name = {e["name"]: e for e in search(client, world["ada"]).json()["items"]}
    assert by_name["Tech Career Fair"]["eligible"] is True and by_name["Marketing Mixer"]["eligible"] is False
    assert by_name["Open House"]["registered"] is True and by_name["Open House"]["registration_count"] == 1
    assert by_name["Resume Workshop"]["registered"] is False
    cara = {e["name"]: e["eligible"] for e in search(client, world["cara"]).json()["items"]}   # Cara has no major
    assert cara == {"Marketing Mixer": False, "Tech Career Fair": False, "Open House": True, "Resume Workshop": True}
    company_view = search(client, world["acme"]).json()["items"][0]
    assert company_view["eligible"] is None and company_view["registered"] is None


def test_list_items_are_light_and_include_expected_fields(client, world):
    item = search(client, world["ada"], q="Mixer").json()["items"][0]
    assert set(item) == {"id", "name", "company", "event_datetime", "location", "city", "eligible_majors",
                         "registration_count", "is_past", "eligible", "registered"}
    assert "description" not in item and item["company"]["name"] == "Acme Corp"


# ===================================================================== details
def test_event_details(client, world):
    e = client.get(f"/events/{world['ids']['tech']}", headers=world["ada"]).json()
    assert e["description"] and e["company"]["name"] == "Acme Corp" and "email" not in e["company"]
    assert e["eligible"] is True and e["can_register"] is True and e["register_blocked_reason"] is None
    m = client.get(f"/events/{world['ids']['mixer']}", headers=world["ada"]).json()
    assert m["can_register"] is False and "Marketing" in m["register_blocked_reason"] and "Computer Science" in m["register_blocked_reason"]
    no_major = client.get(f"/events/{world['ids']['tech']}", headers=world["cara"]).json()
    assert no_major["can_register"] is False and "Add your major" in no_major["register_blocked_reason"]
    past = client.get(f"/events/{world['ids']['old']}", headers=world["ada"]).json()
    assert past["is_past"] is True and past["can_register"] is False and "already taken place" in past["register_blocked_reason"]


def test_event_details_errors(client, world):
    assert client.get("/events/99999", headers=world["ada"]).status_code == 404
    assert client.get("/events/abc", headers=world["ada"]).status_code == 422
    assert client.get(f"/events/{world['ids']['tech']}").status_code == 401


# ===================================================================== register
def test_eligible_student_registers(client, world):
    eid = world["ids"]["tech"]
    r = client.post(f"/events/{eid}/register", headers=world["ada"])
    assert r.status_code == 201
    body = r.json()
    assert body["event"]["name"] == "Tech Career Fair" and body["event"]["registered"] is True
    assert body["event"]["registration_count"] == 1 and body["registered_at"]
    again = client.get(f"/events/{eid}", headers=world["ada"]).json()
    assert again["registered"] is True and again["can_register"] is False and "already registered" in again["register_blocked_reason"]


def test_cannot_register_twice_but_others_can(client, world):
    eid = world["ids"]["open"]
    assert client.post(f"/events/{eid}/register", headers=world["ada"]).status_code == 201
    dup = client.post(f"/events/{eid}/register", headers=world["ada"])
    assert dup.status_code == 409 and "already registered" in dup.json()["detail"]
    assert client.post(f"/events/{eid}/register", headers=world["bob"]).status_code == 201
    assert client.get(f"/events/{eid}", headers=world["ada"]).json()["registration_count"] == 2


def test_ineligible_student_is_refused_with_a_clear_reason(client, world):
    eid = world["ids"]["mixer"]                                    # Marketing only; Ada is Computer Science
    r = client.post(f"/events/{eid}/register", headers=world["ada"])
    assert r.status_code == 403 and "Marketing" in r.json()["detail"] and "Computer Science" in r.json()["detail"]
    assert client.get(f"/events/{eid}/registrations", headers=world["acme"]).json()["total"] == 0
    assert client.post(f"/events/{eid}/register", headers=world["bob"]).status_code == 201     # Bob is Marketing


def test_student_without_a_major_can_only_join_open_events(client, world):
    assert client.post(f"/events/{world['ids']['tech']}/register", headers=world["cara"]).status_code == 403
    assert client.post(f"/events/{world['ids']['open']}/register", headers=world["cara"]).status_code == 201


def test_major_match_ignores_case(client, db, world):
    ada = db.get(models.Student, world["ada_id"])
    ada.major = "computer SCIENCE"
    db.commit()
    assert client.post(f"/events/{world['ids']['tech']}/register", headers=world["ada"]).status_code == 201


def test_cannot_register_for_past_or_missing_events_or_as_other_roles(client, world):
    assert client.post(f"/events/{world['ids']['old']}/register", headers=world["ada"]).status_code == 409
    assert client.post("/events/99999/register", headers=world["ada"]).status_code == 404
    eid = world["ids"]["open"]
    assert client.post(f"/events/{eid}/register").status_code == 401
    assert client.post(f"/events/{eid}/register", headers=world["acme"]).status_code == 403


def test_unregister_and_register_again(client, world):
    eid = world["ids"]["open"]
    client.post(f"/events/{eid}/register", headers=world["ada"])
    assert client.delete(f"/events/{eid}/register", headers=world["ada"]).status_code == 204
    assert client.get(f"/events/{eid}", headers=world["ada"]).json()["registration_count"] == 0
    assert client.delete(f"/events/{eid}/register", headers=world["ada"]).status_code == 404       # nothing left to cancel
    assert client.post(f"/events/{eid}/register", headers=world["ada"]).status_code == 201


def test_cannot_unregister_from_a_past_event(client, db, world):
    db.add(models.EventRegistration(student_id=world["ada_id"], event_id=world["ids"]["old"], registered_at=NOW - timedelta(days=9)))
    db.commit()
    assert client.delete(f"/events/{world['ids']['old']}/register", headers=world["ada"]).status_code == 409


def test_unregister_requires_student(client, world):
    eid = world["ids"]["open"]
    assert client.delete(f"/events/{eid}/register").status_code == 401
    assert client.delete(f"/events/{eid}/register", headers=world["acme"]).status_code == 403


# ===================================================================== my registered events
def test_my_registered_events(client, db, world):
    for key in ("workshop", "open", "tech"):
        assert client.post(f"/events/{world['ids'][key]}/register", headers=world["ada"]).status_code == 201
    db.add(models.EventRegistration(student_id=world["ada_id"], event_id=world["ids"]["old"], registered_at=NOW - timedelta(days=9)))
    db.add(models.EventRegistration(student_id=world["bob_id"], event_id=world["ids"]["mixer"], registered_at=NOW))
    db.commit()
    assert names(client.get("/events/registered", headers=world["ada"])) == ["Tech Career Fair", "Open House", "Resume Workshop"]
    with_past = client.get("/events/registered", params={"include_past": True}, headers=world["ada"])
    assert names(with_past) == ["Old Meetup", "Tech Career Fair", "Open House", "Resume Workshop"]
    assert all(e["registered"] is True for e in with_past.json()["items"])
    assert names(client.get("/events/registered", headers=world["bob"])) == ["Marketing Mixer"]    # only my own
    page = client.get("/events/registered", params={"page_size": 2}, headers=world["ada"]).json()
    assert page["total"] == 3 and page["total_pages"] == 2 and len(page["items"]) == 2


def test_registered_events_requires_student(client, world):
    assert client.get("/events/registered").status_code == 401
    assert client.get("/events/registered", headers=world["acme"]).status_code == 403


# ===================================================================== company: who registered
def test_company_sees_registered_students_and_profiles(client, world):
    eid = world["ids"]["open"]                                      # posted by Globex
    client.post(f"/events/{eid}/register", headers=world["ada"])
    client.post(f"/events/{eid}/register", headers=world["bob"])
    r = client.get(f"/events/{eid}/registrations", headers=world["globex"])
    assert r.status_code == 200
    body = r.json()
    assert body["total"] == 2
    assert [x["student"]["name"] for x in body["items"]] == ["Bob Builder", "Ada Lovelace"]        # most recent first
    ada = body["items"][1]["student"]
    assert ada["email"] == "ada@example.com" and ada["major"] == "Computer Science" and ada["skills"] == ["Python"]
    assert not {"password_hash", "date_of_birth", "experience"} & set(ada)
    assert "password" not in r.text and "hash" not in r.text


def test_registrations_are_private_to_the_owner(client, world):
    eid = world["ids"]["open"]
    client.post(f"/events/{eid}/register", headers=world["ada"])
    url = f"/events/{eid}/registrations"
    assert client.get(url, headers=world["acme"]).status_code == 403          # a different company
    assert client.get(url, headers=world["ada"]).status_code == 403           # a student
    assert client.get(url).status_code == 401
    assert client.get("/events/99999/registrations", headers=world["globex"]).status_code == 404


def test_registrations_pagination(client, world):
    eid = world["ids"]["open"]
    for who in ("ada", "bob", "cara"):
        client.post(f"/events/{eid}/register", headers=world[who])
    page = client.get(f"/events/{eid}/registrations", params={"page_size": 2}, headers=world["globex"]).json()
    assert page["total"] == 3 and page["total_pages"] == 2 and len(page["items"]) == 2


def test_special_routes_are_not_swallowed_by_the_id_route(client, world):
    assert client.get("/events/mine", headers=world["acme"]).status_code == 200
    assert client.get("/events/registered", headers=world["ada"]).status_code == 200