from datetime import datetime, timezone

import frontmatter

from md_converter.core.models import ConversionResult


def inject_frontmatter(result: ConversionResult) -> str:
    meta = {
        "source": result.source_path.name,
        "source_path": str(result.source_path),
        "source_type": result.source_path.suffix.lower(),
        "converter": result.converter_name,
        "converted_at": datetime.now(timezone.utc).isoformat(),
    }
    if result.title:
        meta["title"] = result.title
    if result.warnings:
        meta["warnings"] = result.warnings

    post = frontmatter.Post(result.markdown, **meta)
    return frontmatter.dumps(post)
