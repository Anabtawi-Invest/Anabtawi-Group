def normalize(value):
    if value is None:
        return ""
    return " ".join(str(value).split()).casefold()
