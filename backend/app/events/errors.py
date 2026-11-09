"""Error types shared by the Kafka producers and workers (Lab 2, Part 2)."""


class PermanentError(Exception):
    """A message that can never be processed, however often it is retried (bad JSON, unknown event type, a student
    that does not exist...). A worker sends it straight to the dead-letter topic without retrying."""


class InvalidMessage(PermanentError):
    """The bytes on the topic are not a valid envelope (see KAFKA_CONTRACT.md)."""


class PublishError(Exception):
    """The event could not be handed to Kafka (broker down, delivery timed out)."""
