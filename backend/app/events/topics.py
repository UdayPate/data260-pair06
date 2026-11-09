"""
The Kafka topics of Pair 06. Every topic name starts with the pair prefix "p06." followed by the event type, so the
event type "application.created" travels on the topic "p06.application.created". The full contract (who produces and
consumes each one, the message format) is docs/lab2/KAFKA_CONTRACT.md.
"""
PREFIX = "p06."

APPLICATION_CREATED = "application.created"
APPLICATION_UPDATED = "application.updated"
APPLICATION_STATUS_CHANGED = "application.status_changed"
EVENT_REGISTRATION_CREATED = "event.registration_created"
JOB_CREATED = "job.created"

PARTITIONS = 3                      # one broker, but three partitions let up to three workers share a topic
DLQ_TOPIC = PREFIX + "dlq"          # the dead-letter topic: messages that failed for good end up here

EVENT_TYPES = [APPLICATION_CREATED, APPLICATION_UPDATED, APPLICATION_STATUS_CHANGED,
               EVENT_REGISTRATION_CREATED, JOB_CREATED]


def topic_for(event_type: str) -> str:
    return PREFIX + event_type


# topic name -> number of partitions (created automatically, see events/publisher.py ensure_topics)
TOPICS = {**{topic_for(t): PARTITIONS for t in EVENT_TYPES}, DLQ_TOPIC: 1}
