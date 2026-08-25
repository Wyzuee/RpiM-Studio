# Security

Please do not open public issues containing API keys, passwords, session tokens,
private OAuth secrets, Supabase service-role keys, or database credentials.

RπM Studio expects the Euler API key to remain local to the user's device.
The Supabase key included in `cloud_config.py` is a publishable client key;
never replace it with a `service_role` or `sb_secret_...` key.
