from fractions import Fraction


SHORT_EDGE_OPTIONS = ("原尺寸", "360", "480", "720", "1080", "1440", "1920")


def _resize_by_short_edge(images, short_edge):
    if short_edge == "原尺寸":
        return images
    import torch.nn.functional as functional

    target = int(short_edge)
    height, width = int(images.shape[1]), int(images.shape[2])
    source_short_edge = min(height, width)
    if source_short_edge <= 0 or source_short_edge == target:
        return images
    scale = target / source_short_edge
    target_height = max(1, round(height * scale))
    target_width = max(1, round(width * scale))
    nchw = images.permute(0, 3, 1, 2)
    resized = functional.interpolate(nchw, size=(target_height, target_width), mode="bilinear", align_corners=False)
    return resized.permute(0, 2, 3, 1).contiguous()


def _create_video(images, audio, frame_rate, bit_depth):
    from comfy_api.latest import InputImpl, Types

    components = Types.VideoComponents(
        images=images,
        audio=audio,
        frame_rate=Fraction(str(float(frame_rate))),
    )
    return InputImpl.VideoFromComponents(components, bit_depth=bit_depth)


class MmuuAIVideoImageConverterNode:
    CATEGORY = "MU/媒体处理"
    FUNCTION = "convert"
    RETURN_TYPES = ("VIDEO", "IMAGE")
    RETURN_NAMES = ("视频", "图片序列")

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "图片生成视频帧率": ("FLOAT", {"default": 24.0, "min": 1.0, "max": 120.0, "step": 1.0}),
                "图片生成视频位深": ("INT", {"default": 8, "min": 8, "max": 10, "step": 2}),
                "视频短边尺寸": (list(SHORT_EDGE_OPTIONS), {"default": "原尺寸"}),
            },
            "optional": {
                "视频": ("VIDEO",),
                "图片序列": ("IMAGE",),
            },
        }

    def convert(self, **values):
        video = values.get("视频")
        images = values.get("图片序列")
        if video is None and images is None:
            raise ValueError("必须连接视频或图片序列")

        if video is not None:
            components = video.get_components()
            source_images = components.images
            audio = components.audio
            frame_rate = float(components.frame_rate)
            bit_depth = int(video.get_bit_depth())
        else:
            source_images = images
            audio = None
            frame_rate = float(values["图片生成视频帧率"])
            bit_depth = int(values["图片生成视频位深"])

        conversion_images = images if images is not None else source_images
        resized_images = _resize_by_short_edge(conversion_images, values["视频短边尺寸"])
        if images is None:
            resized_video = _create_video(resized_images, audio, frame_rate, bit_depth)
            return (resized_video, resized_images)

        output_video = _create_video(resized_images, audio, frame_rate, bit_depth)
        return (output_video, resized_images)
