"""Shared source-selection rules for the runner and preparation frontend."""


def vre_profiles_required(sectors, *, model_export=True, model_ready_package=True,
                          require_model_ready=False, existing_only=False):
    return ("power" in sectors and model_export and not existing_only
            and (model_ready_package or require_model_ready))


def skip_vre_for_config(config):
    required = vre_profiles_required(
        ["power"] if config.get("sector_power") else [],
        model_export=config.get("model_export", True),
        model_ready_package=config.get("model_ready_package", True),
        require_model_ready=config.get("require_model_ready", True),
        existing_only=config.get("input_action", "generate") != "generate",
    )
    return bool(config.get("skip_vre")) and not required
