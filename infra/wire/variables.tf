# Required ------------------------------------------------------------------

variable "sec_user_agent" {
  description = "Sent to SEC EDGAR, which asks automated tools for a name and contact email, e.g. \"BCI Census you@example.com\"."
  type        = string
  sensitive   = true

  validation {
    condition     = can(regex("@", var.sec_user_agent))
    error_message = "SEC requires a contact email in the User-Agent, e.g. \"BCI Census you@example.com\"."
  }
}

# Where alerts go: Telegram, ntfy, or both -------------------------------------

variable "telegram_bot_token" {
  description = "Token from @BotFather for your alert bot. Recommended channel on AWS."
  type        = string
  default     = ""
  sensitive   = true

  validation {
    condition     = var.telegram_bot_token == "" || can(regex("^[0-9]+:[A-Za-z0-9_-]+$", var.telegram_bot_token))
    error_message = "A bot token looks like 1234567890:AAE... (digits, a colon, then letters and digits), exactly as @BotFather sent it."
  }
}

variable "telegram_chat_id" {
  description = "Your chat with the bot; `python -m wire telegram-setup` prints it."
  type        = string
  default     = ""

  validation {
    condition     = var.telegram_chat_id == "" || can(regex("^(-?[0-9]+|@[A-Za-z0-9_]+)$", var.telegram_chat_id))
    error_message = "telegram_chat_id is a number such as 123456789 (or -100... for a group or channel)."
  }
}

variable "ntfy_enabled" {
  description = "Also push to ntfy. ntfy.sh's free tier counts messages per IP, and Lambda shares IPs with other AWS customers, so use it with a paid ntfy token or as a second channel."
  type        = bool
  default     = false
}

variable "ntfy_topic" {
  description = "ntfy topic; left empty, a random one is generated (see the ntfy_subscribe_url output)."
  type        = string
  default     = ""
}

variable "ntfy_server" {
  description = "ntfy server."
  type        = string
  default     = "https://ntfy.sh"
}

variable "ntfy_token" {
  description = "ntfy access token (paid ntfy.sh plans are limited per account instead of per IP)."
  type        = string
  default     = ""
  sensitive   = true
}

# When alerts ring ------------------------------------------------------------

variable "timezone" {
  description = "Your time zone (IANA name) for quiet hours and digests, e.g. America/New_York or Europe/Stockholm."
  type        = string
  default     = "America/New_York"
}

variable "quiet_hours" {
  description = "Local hours when only digests are sent, as \"start-end\" (\"23-7\"), or \"off\"."
  type        = string
  default     = "23-7"

  validation {
    condition     = can(regex("^(off|[0-9]{1,2}-[0-9]{1,2})$", var.quiet_hours))
    error_message = "Use \"start-end\" in 24-hour local time, like \"23-7\", or \"off\"."
  }
}

variable "quiet_urgent" {
  description = "Let URGENT alerts (a tracked company's Form D or press release, a tracked program's new trial) ring during quiet hours."
  type        = bool
  default     = false
}

variable "digest_hours" {
  description = "Local hours for the digest of everything held back (quiet hours and low-priority items)."
  type        = list(number)
  default     = [7, 19]

  validation {
    condition     = length(var.digest_hours) > 0 && alltrue([for h in var.digest_hours : h >= 0 && h <= 23 && floor(h) == h])
    error_message = "digest_hours needs at least one whole hour from 0 to 23."
  }
}

# What it watches -------------------------------------------------------------

variable "job_boards" {
  description = "Extra company job boards; the provider and slug are in the careers-page URL (boards.greenhouse.io/<slug>, jobs.lever.co/<slug>, jobs.ashbyhq.com/<slug>)."
  type = list(object({
    program  = optional(string, "")
    provider = string
    slug     = string
  }))
  default = []

  validation {
    condition     = alltrue([for b in var.job_boards : contains(["greenhouse", "lever", "ashby"], b.provider)])
    error_message = "provider must be greenhouse, lever or ashby."
  }
}

variable "disabled_sources" {
  description = "Source names to switch off (see `python -m wire sources`)."
  type        = list(string)
  default     = []
}

variable "site_url" {
  description = "The BCI Census site. Alerts quote its latest census.json for context."
  type        = string
  default     = "https://jikjii.github.io/bci-census/"
}

variable "openfda_api_key" {
  description = "Optional free openFDA key (open.fda.gov) for higher rate limits."
  type        = string
  default     = ""
  sensitive   = true
}

variable "extra_environment" {
  description = "Other Wire settings as environment variables, e.g. { WIRE_NEWS_QUERY = \"...\" }."
  type        = map(string)
  default     = {}
}

# Running it ------------------------------------------------------------------

variable "region" {
  description = "AWS region. us-east-1 sits closest to SEC, FDA and most US news hosts."
  type        = string
  default     = "us-east-1"
}

variable "name" {
  description = "Name for the function and prefix for the other resources."
  type        = string
  default     = "bci-wire"
}

variable "schedule" {
  description = "How often the Wire wakes up. Each source keeps its own interval; the fastest is every minute."
  type        = string
  default     = "rate(1 minute)"
}

variable "paused" {
  description = "true stops the schedule without deleting anything."
  type        = bool
  default     = false
}

variable "memory_mb" {
  description = "Lambda memory. 256 MB is plenty; more memory also means more CPU."
  type        = number
  default     = 256

  validation {
    condition     = var.memory_mb >= 128 && var.memory_mb <= 1024
    error_message = "memory_mb should be between 128 and 1024."
  }
}

variable "timeout_seconds" {
  description = "Lambda timeout. The Wire stops starting new polls 30 seconds before it; runs never overlap."
  type        = number
  default     = 120

  validation {
    condition     = var.timeout_seconds >= 60 && var.timeout_seconds <= 165
    error_message = "timeout_seconds should be between 60 and 165 (the run lock lasts 170 seconds)."
  }
}

variable "log_retention_days" {
  description = "How long CloudWatch keeps the run logs."
  type        = number
  default     = 14

  validation {
    condition     = contains([1, 3, 5, 7, 14, 30, 60, 90, 120, 150, 180, 365], var.log_retention_days)
    error_message = "Use a CloudWatch retention value: 1, 3, 5, 7, 14, 30, 60, 90, 120, 150, 180 or 365."
  }
}

# Cost guardrail ----------------------------------------------------------------

variable "budget_email" {
  description = "Where AWS Budgets sends cost alerts. Empty skips the budget."
  type        = string
  default     = ""
}

variable "monthly_budget_usd" {
  description = "Monthly budget for the whole AWS account. Alerts at 50% and 100% of actual spend and at 100% forecast."
  type        = number
  default     = 10

  validation {
    condition     = var.monthly_budget_usd > 0
    error_message = "monthly_budget_usd must be more than 0."
  }
}
