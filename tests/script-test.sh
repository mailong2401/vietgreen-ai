python3 -c "
from pypdf import PdfReader
r = PdfReader('/home/long/btnpt.pdf')  # sửa path
text = ''.join(p.extract_text() or '' for p in r.pages)

print('Tổng ký tự:', len(text))
print()

kws = {
    'scope 1': 0, 'scope 2': 0, 'scope 3': 0,
    'phát thải': 0, 'tco2': 0, 'tco2e': 0,
    'kwh': 0, 'điện': 0, 'năng lượng': 0,
    'nước': 0, 'm3': 0,
    'chất thải': 0, 'tấn': 0, 'tái chế': 0,
    'sản lượng': 0, 'sản xuất': 0,
    'nhà cung cấp': 0,
}
for kw in kws:
    c = text.lower().count(kw.lower())
    status = '✅' if c >= 3 else ('⚠️' if c > 0 else '❌')
    print(f'{status} {kw:20s}: {c}')
"
