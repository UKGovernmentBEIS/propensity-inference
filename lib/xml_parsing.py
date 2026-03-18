import re


def extract_xml_tag(text: str, tag: str) -> str:
    """Extract content from XML-style tag."""
    pattern = f"<{tag}>(.*?)</{tag}>"
    match = re.search(pattern, text, re.DOTALL | re.IGNORECASE)
    return match.group(1).strip() if match else ""


def remove_text_between_tags(text, tag_name):
    """Remove text between specific XML tags."""
    pattern = f"<{tag_name}[^>]*>.*?</{tag_name}>"
    result = re.sub(pattern, "", text, flags=re.DOTALL)
    return result
