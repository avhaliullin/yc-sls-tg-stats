data "archive_file" "tg_stats_src" {
  output_path = "${path.module}/dist/watchdog-src.zip"
  type        = "zip"
  source_dir  = "${path.module}/src"
}

resource "yandex_iam_service_account" "tg_stats_function" {
  name = "tg-stats-function"
}

resource "yandex_resourcemanager_folder_iam_member" "tg_stats_loader_read_secrets" {
  folder_id = var.folder-id
  role      = "lockbox.payloadViewer"
  member    = "serviceAccount:${yandex_iam_service_account.tg_stats_function.id}"
}

resource "yandex_function" "tg_stats" {
  entrypoint         = "function_handler.run"
  memory             = 512
  name               = "tg-stats-loader"
  runtime            = "python311"
  user_hash          = data.archive_file.tg_stats_src.output_base64sha256
  execution_timeout  = 300
  service_account_id = yandex_iam_service_account.tg_stats_function.id
  content {
    zip_filename = data.archive_file.tg_stats_src.output_path
  }
  environment = {
    CH_CA_CERT_PATH = "/usr/local/share/ca-certificates/yandex-internal-ca.crt"
    CH_HOST         = var.ch-host
    CH_DB           = var.ch-db-name
    DIALOG_IDS      = var.dialog-ids
  }
  secrets {
    id                   = data.yandex_lockbox_secret.tg_secret.id
    version_id           = data.yandex_lockbox_secret.tg_secret.current_version[0].id
    key                  = "api-id"
    environment_variable = "API_ID"
  }
  secrets {
    id                   = data.yandex_lockbox_secret.tg_secret.id
    version_id           = data.yandex_lockbox_secret.tg_secret.current_version[0].id
    key                  = "api-hash"
    environment_variable = "API_HASH"
  }
  secrets {
    id                   = data.yandex_lockbox_secret.tg_secret.id
    version_id           = data.yandex_lockbox_secret.tg_secret.current_version[0].id
    key                  = "session"
    environment_variable = "SESSION_STR"
  }
  secrets {
    id                   = data.yandex_lockbox_secret.ch_secret.id
    version_id           = data.yandex_lockbox_secret.ch_secret.current_version[0].id
    key                  = "user"
    environment_variable = "CH_USER"
  }
  secrets {
    id                   = data.yandex_lockbox_secret.ch_secret.id
    version_id           = data.yandex_lockbox_secret.ch_secret.current_version[0].id
    key                  = "pass"
    environment_variable = "CH_PASS"
  }
  depends_on = [yandex_resourcemanager_folder_iam_member.tg_stats_loader_read_secrets]
}

resource "yandex_iam_service_account" "tg_stats_trigger" {
  name = "tg-stats-trigger"
}

resource "yandex_function_iam_binding" "tg_stats_trigger_invoke_function" {
  function_id = yandex_function.tg_stats.id
  members     = ["serviceAccount:${yandex_iam_service_account.tg_stats_trigger.id}"]
  role        = "serverless.functions.invoker"
}

resource "yandex_function_trigger" "tg_stats" {
  name = "tg-stats"
  function {
    id                 = yandex_function.tg_stats.id
    service_account_id = yandex_iam_service_account.tg_stats_trigger.id
  }
  timer {
    cron_expression = "*/5 * ? * * *"
  }
  depends_on = [yandex_function_iam_binding.tg_stats_trigger_invoke_function]
}

data "yandex_lockbox_secret" "tg_secret" {
  secret_id = var.tg-secret-id
}
data "yandex_lockbox_secret" "ch_secret" {
  secret_id = var.ch-secret-id
}

# configuration
terraform {
  required_providers {
    yandex = {
      source = "yandex-cloud/yandex"
    }
  }
}

provider "yandex" {
  folder_id = var.folder-id
  token     = var.yc-token
}

variable "folder-id" {
  type = string
}

variable "yc-token" {
  type = string
}

variable "ch-host" {
  type = string
}

variable "ch-db-name" {
  type = string
}

variable "dialog-ids" {
  type = string
}

variable "tg-secret-id" {
  type = string
}

variable "ch-secret-id" {
  type = string
}