import openpyxl
wb = openpyxl.load_workbook('058-SBS-06.xlsx', read_only=True, data_only=True)
sh = wb.active
rows = list(sh.iter_rows(values_only=True))
headers = [str(c).strip() if c is not None else '' for c in rows[0]]
print('Headers:', headers)
desig_idx = headers.index('Designator')
sheet_idx = headers.index('SheetNumber')
desc_idx = headers.index('Description') if 'Description' in headers else -1
comment_idx = headers.index('Comment') if 'Comment' in headers else -1
for row in rows[1:]:
    sheet_val = str(row[sheet_idx] or '').strip()
    desig_val = str(row[desig_idx] or '').strip()
    desc_val = str(row[desc_idx] or '').strip() if desc_idx >= 0 else ''
    comment_val = str(row[comment_idx] or '').strip() if comment_idx >= 0 else ''
    sheets = [s.strip() for s in sheet_val.split(',')]
    if '16' in sheets:
        print(repr(sheet_val).ljust(20), '|', desig_val.ljust(40), '|', comment_val.ljust(20), '|', desc_val)
