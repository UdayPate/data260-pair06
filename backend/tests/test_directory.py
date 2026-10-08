"""
Student directory: search, and WHO CAN SEE WHAT.
Run from backend/:   python -m pytest -q
"""
import pytest

CARD_KEYS = {"id", "name", "email", "college", "major", "degree", "graduation_year", "cgpa", "city", "state",
             "profile_pic_url", "skills"}                                           # what a company sees in a list
EMPLOYER_KEYS = CARD_KEYS | {"country", "career_objective", "phone", "experience"}  # a company's profile view
PEER_KEYS = {"id", "name", "college", "major", "degree", "graduation_year", "profile_pic_url", "skills"}
PEER_PROFILE_KEYS = PEER_KEYS | {"career_objective", "experience"}
SECRETS = ["ada@example.com", "bob@example.com", "(408) 555-0123", "3.91", "2001-04-02", "password"]


def bearer(token):
    return {"Authorization": f"Bearer {token}"}


def signup(client, role, name, email, college="San Jose State University"):
    body = {"name": name, "email": email, "password": "Secret123"}
    body.update({"company": {"location": "San Jose"}, "student": {"college": college}}[role])
    r = client.post(f"/auth/{role}/signup", json=body)
    assert r.status_code == 201, r.text
    return bearer(r.json()["access_token"]), r.json()["user_id"]


@pytest.fixture()
def world(client):
    """Five students and a company.
    Ada  - SJSU,         Computer Science, Python+SQL, full profile (phone, GPA, DOB, city, experience)
    Bob  - Santa Clara,  Marketing,        Marketing+Communication
    Cara - SJSU,         (no major),       Python
    Dan  - De Anza,      Data Science,     SQL+Excel
    eve  - Santa Clara,  Data Science,     Python+Excel+SQL   (lower-case name on purpose)"""
    acme, acme_id = signup(client, "company", "Acme Corp", "hr@acme.com")
    ada, ada_id = signup(client, "student", "Ada Lovelace", "ada@example.com")
    bob, bob_id = signup(client, "student", "Bob Builder", "bob@example.com", "Santa Clara University")
    cara, cara_id = signup(client, "student", "Cara Cole", "cara@example.com")
    dan, dan_id = signup(client, "student", "Dan Davis", "dan@example.com", "De Anza College")
    eve, eve_id = signup(client, "student", "eve adams", "eve@example.com", "Santa Clara University")

    client.patch("/students/me", headers=ada, json={
        "major": "Computer Science", "degree": "MS", "graduation_year": 2027, "skills": ["Python", "SQL"],
        "phone": "(408) 555-0123", "cgpa": 3.91, "date_of_birth": "2001-04-02", "city": "San Jose", "state": "CA",
        "country": "United States", "career_objective": "Build data platforms.",
        "experience": [{"title": "Data Intern", "company": "Everlaw", "start_date": "2025-06-01"}]})
    client.patch("/students/me", headers=bob, json={"major": "Marketing", "skills": ["Marketing", "Communication"]})
    client.patch("/students/me", headers=cara, json={"skills": ["Python"]})
    client.patch("/students/me", headers=dan, json={"major": "Data Science", "skills": ["SQL", "Excel"]})
    client.patch("/students/me", headers=eve, json={"major": "Data Science", "skills": ["Python", "Excel", "SQL"]})
    return {"acme": acme, "ada": ada, "bob": bob, "cara": cara, "dan": dan, "eve": eve,
            "ids": {"ada": ada_id, "bob": bob_id, "cara": cara_id, "dan": dan_id, "eve": eve_id}}


def listing(client, who, **params):
    return client.get("/students", params=params, headers=who)


def names(response):
    assert response.status_code == 200, response.text
    return [s["name"] for s in response.json()["items"]]


# ===================================================================== access
def test_directory_requires_login(client, world):
    assert client.get("/students").status_code == 401
    assert client.get(f"/students/{world['ids']['ada']}").status_code == 401


# ===================================================================== company view
def test_company_sees_all_students_sorted_by_name_ignoring_case(client, world):
    assert names(listing(client, world["acme"])) == ["Ada Lovelace", "Bob Builder", "Cara Cole", "Dan Davis", "eve adams"]
    assert listing(client, world["acme"]).json()["total"] == 5


def test_company_list_shows_contact_and_academic_fields_but_never_dob_phone_or_password(client, world):
    r = listing(client, world["acme"], q="ada")
    ada = r.json()["items"][0]
    assert set(ada) == CARD_KEYS
    assert ada["email"] == "ada@example.com" and ada["cgpa"] == 3.91 and ada["skills"] == ["Python", "SQL"]
    assert "2001-04-02" not in r.text and "(408) 555-0123" not in r.text and "hash" not in r.text and "password" not in r.text


def test_search_by_name_words(client, world):
    assert names(listing(client, world["acme"], q="lovelace")) == ["Ada Lovelace"]
    assert names(listing(client, world["acme"], q="ADA")) == ["Ada Lovelace", "eve adams"]   # substring: "ada" is inside "adams"
    assert names(listing(client, world["acme"], q="builder bob")) == ["Bob Builder"]          # every word, any order
    assert listing(client, world["acme"], q="zelda").json()["total"] == 0


def test_q_also_searches_the_college_name(client, world):
    assert names(listing(client, world["acme"], q="santa clara")) == ["Bob Builder", "eve adams"]
    assert names(listing(client, world["acme"], q="de anza")) == ["Dan Davis"]
    assert names(listing(client, world["acme"], q="ada san jose")) == ["Ada Lovelace"]        # name word + college words


def test_percent_and_underscore_are_not_wildcards(client, world):
    assert listing(client, world["acme"], q="%").json()["total"] == 0
    assert listing(client, world["acme"], q="_").json()["total"] == 0
    assert listing(client, world["acme"], college="%").json()["total"] == 0


def test_college_filter(client, world):
    assert names(listing(client, world["acme"], college="san jose state")) == ["Ada Lovelace", "Cara Cole"]
    assert names(listing(client, world["acme"], college="UNIVERSITY")) == ["Ada Lovelace", "Bob Builder", "Cara Cole", "eve adams"]
    assert names(listing(client, world["acme"], q="lovelace", college="santa clara")) == []


def test_filter_by_major_one_or_several_ignoring_case(client, world):
    assert names(listing(client, world["acme"], major="data science")) == ["Dan Davis", "eve adams"]
    several = client.get("/students", params=[("major", "Marketing"), ("major", "Computer Science")], headers=world["acme"])
    assert names(several) == ["Ada Lovelace", "Bob Builder"]
    assert "Cara Cole" not in names(listing(client, world["acme"], major="Marketing"))      # no major set: never matches


def test_filter_by_skills_any_and_all(client, world):
    assert names(listing(client, world["acme"], skills="python")) == ["Ada Lovelace", "Cara Cole", "eve adams"]
    two = [("skills", "Python"), ("skills", "sql")]
    assert names(client.get("/students", params=two, headers=world["acme"])) == ["Ada Lovelace", "Cara Cole", "Dan Davis", "eve adams"]
    assert names(client.get("/students", params=two + [("skills_match", "all")], headers=world["acme"])) == ["Ada Lovelace", "eve adams"]
    assert listing(client, world["acme"], skills="Welding").json()["total"] == 0


def test_filters_combine_with_and(client, world):
    r = listing(client, world["acme"], major="Data Science", skills="Python", college="santa clara")
    assert names(r) == ["eve adams"]
    assert listing(client, world["acme"], major="Marketing", skills="Python").json()["total"] == 0


def test_pagination(client, world):
    first = listing(client, world["acme"], page_size=2).json()
    assert first["total"] == 5 and first["total_pages"] == 3 and [s["name"] for s in first["items"]] == ["Ada Lovelace", "Bob Builder"]
    assert names(listing(client, world["acme"], page_size=2, page=3)) == ["eve adams"]
    assert listing(client, world["acme"], page=9).json()["items"] == []


@pytest.mark.parametrize("params", [
    {"page": 0}, {"page_size": 0}, {"page_size": 101}, {"skills_match": "some"}, {"q": "x" * 101}, {"college": "x" * 151},
], ids=["page-0", "size-0", "size-101", "bad-match", "long-q", "long-college"])
def test_bad_parameters_rejected(client, world, params):
    assert listing(client, world["acme"], **params).status_code == 422


# ===================================================================== student (peer) view
def test_student_directory_excludes_the_viewer_and_shows_only_peer_fields(client, world):
    r = listing(client, world["ada"])
    assert names(r) == ["Bob Builder", "Cara Cole", "Dan Davis", "eve adams"]            # no Ada
    assert all(set(s) == PEER_KEYS for s in r.json()["items"])
    assert not any(secret in r.text for secret in ["bob@example.com", "cara@example.com", "dan@example.com", "eve@example.com"])


def test_peers_never_get_email_phone_gpa_dob_or_city(client, world):
    r = listing(client, world["bob"], q="ada")                 # Bob looks up Ada, whose profile is fully filled in
    ada = r.json()["items"][0]
    assert ada["name"] == "Ada Lovelace" and ada["major"] == "Computer Science" and ada["skills"] == ["Python", "SQL"]
    for secret in SECRETS + ["San Jose\"", "3.91"]:
        assert secret not in r.text, secret
    assert not {"email", "phone", "cgpa", "date_of_birth", "city", "state"} & set(ada)


def test_students_can_search_and_filter_too(client, world):
    assert names(listing(client, world["ada"], q="santa clara")) == ["Bob Builder", "eve adams"]
    assert names(listing(client, world["ada"], major="Data Science")) == ["Dan Davis", "eve adams"]
    assert names(listing(client, world["bob"], skills="Python")) == ["Ada Lovelace", "Cara Cole", "eve adams"]
    assert names(listing(client, world["ada"], q="lovelace")) == []                     # can't find themselves
    assert listing(client, world["ada"]).json()["total"] == 4


# ===================================================================== profiles
def test_company_opens_a_full_student_profile_without_dob_or_password(client, world):
    r = client.get(f"/students/{world['ids']['ada']}", headers=world["acme"])
    assert r.status_code == 200
    p = r.json()
    assert set(p) == EMPLOYER_KEYS
    assert p["email"] == "ada@example.com" and p["phone"] == "(408) 555-0123" and p["cgpa"] == 3.91
    assert p["career_objective"] == "Build data platforms." and p["city"] == "San Jose" and p["country"] == "United States"
    assert p["experience"][0]["company"] == "Everlaw" and p["skills"] == ["Python", "SQL"]
    assert "2001-04-02" not in r.text and "date_of_birth" not in r.text and "hash" not in r.text


def test_student_opens_a_limited_peer_profile(client, world):
    r = client.get(f"/students/{world['ids']['ada']}", headers=world["bob"])
    assert r.status_code == 200
    p = r.json()
    assert set(p) == PEER_PROFILE_KEYS
    assert p["career_objective"] == "Build data platforms." and p["experience"][0]["title"] == "Data Intern"
    for secret in SECRETS + ["San Jose\"", "United States"]:
        assert secret not in r.text, secret


def test_profile_errors(client, world):
    assert client.get("/students/99999", headers=world["acme"]).status_code == 404
    assert client.get("/students/99999", headers=world["ada"]).status_code == 404
    assert client.get("/students/abc", headers=world["acme"]).status_code == 422


def test_me_route_still_belongs_to_the_students_own_profile(client, world):
    me = client.get("/students/me", headers=world["ada"])
    assert me.status_code == 200 and me.json()["email"] == "ada@example.com"
    assert me.json()["date_of_birth"] == "2001-04-02"                  # the student's OWN view still includes it
    assert client.get("/students/me", headers=world["acme"]).status_code == 403     # companies have no /me student profile
    assert client.get("/students/me").status_code == 401


def test_a_student_viewing_their_own_id_gets_the_peer_view(client, world):
    p = client.get(f"/students/{world['ids']['ada']}", headers=world["ada"]).json()
    assert set(p) == PEER_PROFILE_KEYS


def test_changes_to_a_profile_show_up_in_the_directory(client, world):
    client.patch("/students/me", headers=world["cara"], json={"major": "Marketing", "skills": ["Marketing"]})
    assert "Cara Cole" in names(listing(client, world["acme"], major="Marketing"))
    assert "Cara Cole" not in names(listing(client, world["acme"], skills="Python"))