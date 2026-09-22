import io


def video_upload(video, index):
    source = video.get_stream_source()
    if isinstance(source, str):
        with open(source, "rb") as handle:
            data = handle.read()
    else:
        source.seek(0)
        data = source.read()
        source.seek(0)
    container = video.get_container_format().split(",", 1)[0].lower()
    mime_type = {
        "mp4": "video/mp4",
        "mov": "video/quicktime",
        "quicktime": "video/quicktime",
        "mpeg": "video/mpeg",
        "mpegvideo": "video/mpeg",
        "avi": "video/x-msvideo",
        "webm": "video/webm",
        "flv": "video/x-flv",
        "wmv": "video/x-ms-wmv",
        "3gp": "video/3gpp",
        "3gpp": "video/3gpp",
    }.get(container)
    if not mime_type:
        raise ValueError(f"不支持当前视频容器格式：{container}")
    extension = "mov" if container == "quicktime" else container
    return data, f"video-{index}.{extension}", mime_type


def uploaded_file(client, data, media_kind, file_name, mime_type, parameter):
    upload = client.upload(data, media_kind, file_name, mime_type)
    reference = upload.get("ref") if isinstance(upload, dict) else None
    if not isinstance(reference, str) or not reference:
        raise RuntimeError("mmuuai 上传接口未返回文件引用")
    return {
        "source": {"type": "upload", "ref": reference},
        "mediaKind": media_kind,
        "fileName": file_name,
        "mimeType": mime_type,
        **({"parameter": parameter} if parameter else {}),
    }
