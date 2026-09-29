from dbfread import DBF


def open_dbf(file_path):
    return DBF(
        file_path,
        load=False,
        char_decode_errors="ignore"
    )


def get_field_names(db):
    return list(db.field_names)


def get_record_count(db):
    return len(db)


def iter_records(db):
    for record in db:
        yield dict(record)