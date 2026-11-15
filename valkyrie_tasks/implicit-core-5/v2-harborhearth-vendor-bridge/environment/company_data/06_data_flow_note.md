# GuestPulse integration note

The nightly connector sends new guest and survey records from the property-management system at 02:00 local time. This connector can be paused centrally without deleting historical records.

GuestPulse confirms that dashboard users retain read-only access to previously ingested reports when the connector is paused. Report export also remains available. New surveys and profile changes will not appear until ingestion resumes.
