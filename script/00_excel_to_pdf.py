#!/usr/bin/env python
# Auto-generated from 00_excel_to_pdf.ipynb

import os as _os, sys as _sys
_HERE = _os.path.dirname(_os.path.abspath(__file__))
_sys.path.insert(0, _os.path.dirname(_HERE))  # import utils_cc from parent (customChunkPipeline)
_os.chdir(_os.path.dirname(_HERE))       # run as if from customChunkPipeline/

import os, shutil, subprocess
from pathlib import Path
from dotenv import load_dotenv

load_dotenv('../.env', override=True)  # ./.env (project root)
load_dotenv(override=True)  # local .env overrides if present

DATA_DIR = Path('../data')   # ソースドキュメント
PDF_DIR  = Path('./pdf')     # 処理対象の PDF 置き場
PDF_DIR.mkdir(parents=True, exist_ok=True)
print('data files:', [p.name for p in DATA_DIR.iterdir()] if DATA_DIR.exists() else 'NO data dir')

def find_soffice():
    for name in ('soffice', 'soffice.exe', 'libreoffice'):
        path = shutil.which(name)
        if path:
            return path
    # Common Windows install locations
    for cand in (r'C:\Program Files\LibreOffice\program\soffice.exe',
                 r'C:\Program Files (x86)\LibreOffice\program\soffice.exe'):
        if Path(cand).exists():
            return cand
    return None

def excel_to_pdf_soffice(soffice, xlsx_path, out_dir):
    subprocess.run([soffice, '--headless', '--calc', '--convert-to', 'pdf',
                    '--outdir', str(out_dir), str(xlsx_path)], check=True)

def excel_to_pdf_com(xlsx_path, pdf_path):
    # Windows + Microsoft Excel only
    import win32com.client as win32
    excel = win32.DispatchEx('Excel.Application')
    excel.Visible = False
    excel.DisplayAlerts = False
    try:
        wb = excel.Workbooks.Open(str(xlsx_path.resolve()))
        # 0 = xlTypePDF
        wb.ExportAsFixedFormat(0, str(pdf_path.resolve()))
        wb.Close(False)
    finally:
        excel.Quit()

soffice = find_soffice()
print('LibreOffice:', soffice or 'not found (will try Excel COM on Windows)')

for src in sorted(DATA_DIR.iterdir()):
    if src.suffix.lower() == '.pdf':
        dst = PDF_DIR / src.name
        shutil.copy2(src, dst)
        print('copied PDF :', src.name)
    elif src.suffix.lower() in ('.xlsx', '.xls'):
        pdf_path = PDF_DIR / (src.stem + '.pdf')
        if soffice:
            excel_to_pdf_soffice(soffice, src, PDF_DIR)
        else:
            excel_to_pdf_com(src, pdf_path)
        print('converted  :', src.name, '->', pdf_path.name)

print('\nPDF dir now contains:', [p.name for p in PDF_DIR.glob('*.pdf')])
