"""
Shared vocabularies used by BOTH the seed generator (Part A) and the
assistant tools (Part B). Import from here; never retype these strings.

Convention: values are stored in Title Case exactly as written below.
Searches should compare case-insensitively (e.g. func.lower(...)).
"""

SKILLS_BY_AREA = {
    "programming": ["Python", "Java", "JavaScript", "TypeScript", "C++", "SQL", "R", "Go"],
    "web": ["React", "Node.js", "FastAPI", "Django", "HTML", "CSS", "REST APIs"],
    "data_ml": [
        "Machine Learning", "Deep Learning", "Data Analysis", "Statistics", "Pandas",
        "PyTorch", "TensorFlow", "NLP", "Tableau", "Excel",
    ],
    "data_eng_cloud": ["Spark", "Kafka", "Airflow", "AWS", "Docker", "Kubernetes", "ETL"],
    "non_technical": [
        "Communication", "Project Management", "Marketing", "Customer Service", "Event Planning",
    ],
}
ALL_SKILLS = [s for group in SKILLS_BY_AREA.values() for s in group]

MAJORS = [
    "Computer Science", "Data Science", "Software Engineering", "Computer Engineering",
    "Electrical Engineering", "Business Analytics", "Information Systems",
    "Marketing", "Mathematics", "Statistics",
]

COLLEGES = [
    "San Jose State University", "Santa Clara University", "Stanford University",
    "De Anza College", "Foothill College", "UC Santa Cruz",
]

DEGREES = ["BS", "MS"]

# Job "fields": each picks titles and a skill pool so jobs look coherent.
JOB_FIELDS = {
    "data": {
        "titles": ["Data Analyst", "Data Science", "Machine Learning Engineer",
                   "Data Engineer", "Business Intelligence Analyst"],
        "skills": SKILLS_BY_AREA["data_ml"] + SKILLS_BY_AREA["data_eng_cloud"] + ["Python", "SQL", "R"],
    },
    "software": {
        "titles": ["Software Engineer", "Backend Developer", "Frontend Developer",
                   "Full Stack Developer", "QA Engineer"],
        "skills": SKILLS_BY_AREA["programming"] + SKILLS_BY_AREA["web"] + ["Docker", "AWS"],
    },
    "web": {
        "titles": ["Web Developer", "Web Development and Design", "WordPress Developer"],
        "skills": SKILLS_BY_AREA["web"] + ["JavaScript", "TypeScript"],
    },
    "business": {
        "titles": ["Marketing Associate", "Business Analyst", "Sales Development Representative",
                   "Project Coordinator"],
        "skills": SKILLS_BY_AREA["non_technical"] + ["Excel", "Tableau", "Data Analysis"],
    },
}

# On-campus job titles (posted only by the campus employers in the seed).
CAMPUS_TITLES = ["Library Assistant", "IT Help Desk Assistant", "Event Service Assistant",
                 "Peer Tutor", "Research Assistant"]
CAMPUS_SKILLS = ["Customer Service", "Communication", "Excel", "Python", "Event Planning"]

# Deliberately ABSENT from the seed data. Part B test 5 asks for one of these and
# the assistant must say no match exists instead of inventing one.
ABSENT_FROM_SEED = ["Nursing", "Veterinary", "Pilot", "Pharmacist", "Tesla", "NASA"]