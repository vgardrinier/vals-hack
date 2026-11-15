# GuestPulse access map

Historical dashboard reads use the analytics service account. New PMS ingestion uses a separate connector credential. Disabling the connector does not disable dashboard reads or exports.

The analytics service account expires in five days; extending it through a bridge requires the same Security and Risk approval as the bridge itself.
