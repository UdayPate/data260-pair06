"""
Writes the five Apache JMeter test plans (.jmx) for Lab 2, Part 5.

    python jmeter/generate_plans.py          (from the repo root; writes jmeter/plans/*.jmx)

JMeter stores a test plan as XML. Writing 5 similar XML files by hand invites typos, so this script builds them from the
same few pieces (a thread group, a data file reader, a login step, the requests of the scenario). The generated files are
committed, so JMeter can open them directly; run this script again only when the scenarios change.

The five scenarios (plan name -> what each virtual user does):
  login        POST /auth/login                                                   (100, 200, 300, 400, 500 users)
  job_search   log in once, then GET /jobs with a random filter, several times    (100 ... 500 users)
  apply        log in once, then POST /jobs/{id}/apply with a PDF (answer 202)    (100 ... 500 users)
  events       log in once, GET /events, then POST /events/{id}/register (201)    (100 ... 500 users)
  assistant    log in once, then POST /assistant/chat with a question             (5, 10, 20, 50 users)

Everything that changes between runs is a JMeter PROPERTY, given on the command line with -J (see run_load_tests.py):
  threads (number of virtual users), ramp (seconds to start them all), loops (requests per user), host, port,
  data (the folder with the CSV files), think (milliseconds of "thinking" between requests), response_timeout.
A request whose label starts with "SETUP" (the login of the other scenarios) or "INFO" is not counted in the results.
"""
from pathlib import Path
from xml.sax.saxutils import escape

PLANS = Path(__file__).resolve().parent / "plans"
JMETER_VERSION = "5.6.3"


def prop(name, value, kind="stringProp"):
    return f'<{kind} name="{name}">{escape(str(value))}</{kind}>'


def header_manager(headers):
    rows = "".join(f'<elementProp name="" elementType="Header">{prop("Header.name", k)}{prop("Header.value", v)}</elementProp>'
                   for k, v in headers.items())
    return ('<HeaderManager guiclass="HeaderPanel" testclass="HeaderManager" testname="Headers" enabled="true">'
            f'<collectionProp name="HeaderManager.headers">{rows}</collectionProp></HeaderManager><hashTree/>')


def http_defaults():
    return ('<ConfigTestElement guiclass="HttpDefaultsGui" testclass="ConfigTestElement" testname="HTTP Request Defaults" enabled="true">'
            '<elementProp name="HTTPsampler.Arguments" elementType="Arguments" guiclass="HTTPArgumentsPanel" testclass="Arguments" '
            'testname="User Defined Variables" enabled="true"><collectionProp name="Arguments.arguments"/></elementProp>'
            + prop("HTTPSampler.domain", "${__P(host,localhost)}") + prop("HTTPSampler.port", "${__P(port,9060)}")
            + prop("HTTPSampler.protocol", "http") + prop("HTTPSampler.contentEncoding", "UTF-8")
            + prop("HTTPSampler.connect_timeout", "5000") + prop("HTTPSampler.response_timeout", "${__P(response_timeout,30000)}")
            + '</ConfigTestElement><hashTree/>')


def csv_data(name, filename, variables):
    """Reads one row of a CSV file per virtual user (and per loop), sharing the file between all users."""
    return ('<CSVDataSet guiclass="TestBeanGUI" testclass="CSVDataSet" testname="%s" enabled="true">' % escape(name)
            + prop("delimiter", ",") + prop("fileEncoding", "UTF-8") + prop("filename", "${__P(data,jmeter/data)}/" + filename)
            + prop("ignoreFirstLine", "true", "boolProp") + prop("quotedData", "true", "boolProp") + prop("recycle", "true", "boolProp")
            + prop("shareMode", "shareMode.all") + prop("stopThread", "false", "boolProp") + prop("variableNames", variables)
            + '</CSVDataSet><hashTree/>')


def status_assertion(code):
    """Fails the sample unless the HTTP status is exactly `code` (test_type 8 = 'equals')."""
    return ('<ResponseAssertion guiclass="AssertionGui" testclass="ResponseAssertion" testname="status is %s" enabled="true">'
            '<collectionProp name="Asserion.test_strings">%s</collectionProp>' % (code, prop("1", code))
            + prop("Assertion.custom_message", "") + prop("Assertion.test_field", "Assertion.response_code")
            + prop("Assertion.assume_success", "false", "boolProp") + prop("Assertion.test_type", "8", "intProp")
            + '</ResponseAssertion><hashTree/>')


def token_extractor():
    return ('<JSONPostProcessor guiclass="JSONPostProcessorGui" testclass="JSONPostProcessor" testname="keep the token" enabled="true">'
            + prop("JSONPostProcessor.referenceNames", "token") + prop("JSONPostProcessor.jsonPathExprs", "$.access_token")
            + prop("JSONPostProcessor.match_numbers", "1") + prop("JSONPostProcessor.defaultValues", "NOTOKEN")
            + '</JSONPostProcessor><hashTree/>')


def sampler(label, method, path, expect, *, body=None, query=None, file=None, children=""):
    """One HTTP request. body = a raw JSON text; query = {name: value}; file = (path, form field, mime type)."""
    arguments = ""
    if body is not None:
        arguments = ('<elementProp name="" elementType="HTTPArgument">' + prop("HTTPArgument.always_encode", "false", "boolProp")
                     + prop("Argument.value", body) + prop("Argument.metadata", "=") + '</elementProp>')
    for name, value in (query or {}).items():
        arguments += ('<elementProp name="%s" elementType="HTTPArgument">' % escape(name) + prop("HTTPArgument.always_encode", "false", "boolProp")
                      + prop("Argument.value", value) + prop("Argument.metadata", "=") + prop("HTTPArgument.use_equals", "true", "boolProp")
                      + prop("Argument.name", name) + '</elementProp>')
    files = ""
    if file:
        files = ('<elementProp name="HTTPsampler.Files" elementType="HTTPFileArgs"><collectionProp name="HTTPFileArgs.files">'
                 '<elementProp name="%s" elementType="HTTPFileArg">' % escape(file[0]) + prop("File.path", file[0])
                 + prop("File.paramname", file[1]) + prop("File.mimetype", file[2]) + '</elementProp></collectionProp></elementProp>')
    return ('<HTTPSamplerProxy guiclass="HttpTestSampleGui" testclass="HTTPSamplerProxy" testname="%s" enabled="true">' % escape(label)
            + prop("HTTPSampler.postBodyRaw", "true" if body is not None else "false", "boolProp")
            + '<elementProp name="HTTPsampler.Arguments" elementType="Arguments" guiclass="HTTPArgumentsPanel" testclass="Arguments" '
              'testname="User Defined Variables" enabled="true"><collectionProp name="Arguments.arguments">%s</collectionProp></elementProp>' % arguments
            + files + prop("HTTPSampler.path", path) + prop("HTTPSampler.method", method)
            + prop("HTTPSampler.follow_redirects", "true", "boolProp") + prop("HTTPSampler.auto_redirects", "false", "boolProp")
            + prop("HTTPSampler.use_keepalive", "true", "boolProp") + prop("HTTPSampler.DO_MULTIPART_POST", "true" if file else "false", "boolProp")
            + '</HTTPSamplerProxy><hashTree>' + status_assertion(expect) + children + '</hashTree>')


def think_time():
    return ('<ConstantTimer guiclass="ConstantTimerGui" testclass="ConstantTimer" testname="think time" enabled="true">'
            + prop("ConstantTimer.delay", "${__P(think,500)}") + '</ConstantTimer><hashTree/>')


def login_step(label):
    body = '{"email":"${email}","password":"${password}","role":"${role}"}'
    return sampler(label, "POST", "/auth/login", 200, body=body, children=header_manager({"Content-Type": "application/json"}) + token_extractor())


def once_only(title, inner):
    return ('<OnceOnlyController guiclass="OnceOnlyControllerGui" testclass="OnceOnlyController" testname="%s" enabled="true"/>'
            '<hashTree>%s</hashTree>' % (escape(title), inner))


def thread_group(name, inner):
    return ('<ThreadGroup guiclass="ThreadGroupGui" testclass="ThreadGroup" testname="%s" enabled="true">' % escape(name)
            + prop("ThreadGroup.on_sample_error", "continue")
            + '<elementProp name="ThreadGroup.main_controller" elementType="LoopController" guiclass="LoopControlPanel" '
              'testclass="LoopController" testname="Loop Controller" enabled="true">'
            + prop("LoopController.continue_forever", "false", "boolProp") + prop("LoopController.loops", "${__P(loops,1)}")
            + '</elementProp>' + prop("ThreadGroup.num_threads", "${__P(threads,100)}") + prop("ThreadGroup.ramp_time", "${__P(ramp,30)}")
            + prop("ThreadGroup.scheduler", "false", "boolProp") + prop("ThreadGroup.same_user_on_next_iteration", "true", "boolProp")
            + '</ThreadGroup><hashTree>' + inner + '</hashTree>')


def plan(title, description, inner):
    return ('<?xml version="1.0" encoding="UTF-8"?>\n'
            f'<jmeterTestPlan version="1.2" properties="5.0" jmeter="{JMETER_VERSION}"><hashTree>'
            '<TestPlan guiclass="TestPlanGui" testclass="TestPlan" testname="%s" enabled="true">' % escape(title)
            + prop("TestPlan.comments", description) + prop("TestPlan.functional_mode", "false", "boolProp")
            + prop("TestPlan.tearDown_on_shutdown", "true", "boolProp") + prop("TestPlan.serialize_threadgroups", "false", "boolProp")
            + '<elementProp name="TestPlan.user_defined_variables" elementType="Arguments" guiclass="ArgumentsPanel" testclass="Arguments" '
              'testname="User Defined Variables" enabled="true"><collectionProp name="Arguments.arguments"/></elementProp>'
            + prop("TestPlan.user_define_classpath", "") + '</TestPlan><hashTree>' + http_defaults() + inner + '</hashTree></hashTree></jmeterTestPlan>\n')


AUTH_HEADER = header_manager({"Authorization": "Bearer ${token}"})
STUDENTS = csv_data("students.csv", "students.csv", "email,password,role")


def build_plans():
    plans = {}

    plans["login"] = plan(
        "p06 login", "Each virtual user signs in once as a seeded student. Run with threads=100,200,300,400,500.",
        thread_group("Users sign in", STUDENTS + login_step("login") ))

    searches = once_only("Once only: sign in", login_step("SETUP login")) + (
        '<RandomController guiclass="RandomControlGui" testclass="RandomController" testname="a random job search" enabled="true">'
        + prop("InterleaveControl.style", "1", "intProp") + '</RandomController><hashTree>'
        + sampler("job search by title", "GET", "/jobs", 200, query={"q": "data", "page": "${__Random(1,3)}", "page_size": "10"})
        + sampler("job search by city", "GET", "/jobs", 200, query={"city": "San Jose", "page_size": "10"})
        + sampler("job search remote internships", "GET", "/jobs", 200, query={"category": "internship", "is_remote": "true", "sort": "salary"})
        + sampler("job search by skill", "GET", "/jobs", 200, query={"skills": "Python", "skills_match": "any", "page_size": "10"})
        + '</hashTree>' + think_time())
    plans["job_search"] = plan(
        "p06 job search", "Each user signs in once (not counted), then searches jobs with a random filter, loops times.",
        thread_group("Users search jobs", AUTH_HEADER + STUDENTS + searches))

    apply_requests = once_only("Once only: sign in", login_step("SETUP login")) + sampler(
        "apply for a job", "POST", "/jobs/${job_id}/apply", 202, file=("${__P(data,jmeter/data)}/resume.pdf", "resume", "application/pdf")) + (
        '<ConstantTimer guiclass="ConstantTimerGui" testclass="ConstantTimer" testname="give the worker 3 s" enabled="true">'
        + prop("ConstantTimer.delay", "3000") + '</ConstantTimer><hashTree/>') + sampler(
        "INFO job page after apply (my_application set?)", "GET", "/jobs/${job_id}", 200)
    plans["apply"] = plan(
        "p06 apply through Kafka",
        "Each user signs in once (not counted) and applies to a job nobody applied to yet: the API answers 202 and a Kafka worker "
        "saves the application. The INFO request afterwards only shows whether the worker had finished; it is not counted.",
        thread_group("Users apply", AUTH_HEADER + csv_data("apply_pairs.csv", "apply_pairs.csv", "email,password,role,job_id") + apply_requests))

    event_requests = once_only("Once only: sign in", login_step("SETUP login")) + sampler(
        "event search", "GET", "/events", 200, query={"page": "${__Random(1,3)}", "page_size": "10"}) + think_time() + sampler(
        "event register", "POST", "/events/${event_id}/register", 201)
    plans["events"] = plan(
        "p06 event search and registration",
        "Each user signs in once (not counted), searches events, then registers for an event they are eligible for and are not registered for.",
        thread_group("Users search and register", AUTH_HEADER + csv_data("event_pairs.csv", "event_pairs.csv", "email,password,role,event_id") + event_requests))

    chat_body = '{"message":"${message}","conversation_id":null}'
    assistant_requests = once_only("Once only: sign in", login_step("SETUP login")) + sampler(
        "assistant chat", "POST", "/assistant/chat", 200, body=chat_body, children=header_manager({"Content-Type": "application/json"}))
    plans["assistant"] = plan(
        "p06 assistant chat",
        "Each user signs in once (not counted), then asks the assistant a question. Run with threads=5,10,20,50 and a long "
        "response_timeout: a model on a CPU can take minutes per answer.",
        thread_group("Users chat", AUTH_HEADER + csv_data("students.csv", "students.csv", "email,password,role")
                     + csv_data("assistant_messages.csv", "assistant_messages.csv", "message") + assistant_requests))
    return plans


def main():
    PLANS.mkdir(parents=True, exist_ok=True)
    for name, xml in build_plans().items():
        (PLANS / f"{name}.jmx").write_text(xml, encoding="utf-8")
        print(f"wrote jmeter/plans/{name}.jmx")


if __name__ == "__main__":
    main()
