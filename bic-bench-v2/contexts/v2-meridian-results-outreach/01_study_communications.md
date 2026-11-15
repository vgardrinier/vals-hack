# MG-27 communication resolution workflow

For each result, the send control resolves three live profile fields: `result_channel`, `clinical_language`, and `authorized_viewers`. Historical exports populate migration reconciliation only. A proxy appears in `authorized_viewers` only while portal access is active.

If the assigned coordinator lacks the validation badge for `clinical_language`, the workflow state is `Draft → Bilingual review → Send`. Appointment logistics may be prepared while review is pending, but clinical content follows the resolved channel.
