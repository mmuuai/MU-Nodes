def build_parameters(resource, requested):
    definitions = _definitions(resource)
    output = {}
    for candidates, value, mode in requested:
        if value is None:
            continue
        definition = _find(definitions, candidates)
        if definition is None:
            continue
        converted = _convert(definition, value, mode)
        if converted is not None:
            output[definition["name"]] = converted
    return output


def upload_parameter(resource, media_kind):
    for definition in _definitions(resource):
        upload = definition.get("upload")
        if isinstance(upload, dict) and upload.get("kind") == media_kind:
            return definition["name"]
    return None


def _definitions(resource):
    capabilities = resource.get("inputCapabilities")
    if not isinstance(capabilities, dict):
        return []
    parameters = capabilities.get("parameters")
    return [item for item in parameters if isinstance(item, dict) and item.get("name")] if isinstance(parameters, list) else []


def _find(definitions, candidates):
    wanted = {_key(value) for value in candidates}
    for definition in definitions:
        if _key(definition.get("name")) in wanted:
            return definition
    return None


def _convert(definition, value, mode):
    if mode == "number":
        number = float(value)
        range_value = definition.get("range")
        if isinstance(range_value, dict):
            minimum, maximum = range_value.get("min"), range_value.get("max")
            if isinstance(minimum, (int, float)):
                number = max(number, minimum)
            if isinstance(maximum, (int, float)):
                number = min(number, maximum)
        return int(number) if definition.get("valueType") == "integer" else number
    if mode == "semantic":
        return _semantic_option(definition, value)
    if mode == "option":
        return _matching_option(definition, value)
    return value


def _semantic_option(definition, value):
    aliases = {
        "最少": ("none", "minimal", "min"),
        "低": ("low",),
        "中": ("medium", "med"),
        "高": ("high",),
        "极高": ("xhigh", "very_high", "very high"),
        "最高": ("max", "maximum", "xhigh"),
        "简洁": ("low", "concise", "short"),
        "标准": ("medium", "normal", "standard"),
        "详细": ("high", "detailed", "verbose"),
        "专业": ("pro", "professional"),
    }
    for candidate in aliases.get(str(value), (str(value),)):
        matched = _matching_option(definition, candidate)
        if matched is not None:
            return matched
    return None


def _matching_option(definition, value):
    options = definition.get("options")
    if not isinstance(options, list) or not options:
        return value
    target = _key(value)
    for option in options:
        if not isinstance(option, dict):
            continue
        if target in (_key(option.get("value")), _key(option.get("label"))):
            return option.get("value")
    return None


def _key(value):
    return str(value or "").strip().casefold().replace("_", "").replace(".", "")
