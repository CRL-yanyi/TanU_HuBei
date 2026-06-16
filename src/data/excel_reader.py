# -*- coding: utf-8 -*-
import pandas as pd
import xml.etree.ElementTree as ET
from typing import Dict

def parse_xml_spreadsheet(file_path: str) -> Dict[str, pd.DataFrame]:
    """
    解析 XML Spreadsheet 2003 格式 of Excel file, with special characters tolerance.
    """
    namespaces = {'ss': 'urn:schemas-microsoft-com:office:spreadsheet'}
    with open(file_path, 'rb') as f:
        content = f.read()
    
    # 预处理：替换未转义的 & 符号，防止 XML 解析器报错
    content = content.replace(b'&', b'&amp;')
    content = content.replace(b'&amp;amp;', b'&amp;')
    content = content.replace(b'&amp;lt;', b'&lt;')
    content = content.replace(b'&amp;gt;', b'&gt;')
    content = content.replace(b'&amp;quot;', b'&quot;')
    content = content.replace(b'&amp;apos;', b'&apos;')
    
    # 解码
    try:
        content_str = content.decode('utf-8')
    except UnicodeDecodeError:
        content_str = content.decode('gbk', errors='ignore')
        
    root = ET.fromstring(content_str.encode('utf-8'))
    worksheets = root.findall('.//ss:Worksheet', namespaces)
    sheets_dict = {}
    
    for ws in worksheets:
        sheet_name = ws.get('{urn:schemas-microsoft-com:office:spreadsheet}Name')
        table = ws.find('.//ss:Table', namespaces)
        if table is None:
            continue
            
        rows_data = []
        rows = table.findall('.//ss:Row', namespaces)
        for r in rows:
            cells_data = []
            cells = r.findall('.//ss:Cell', namespaces)
            for c in cells:
                # 处理可能包含的 ss:Index 属性（跳过空列）
                index_attr = c.get('{urn:schemas-microsoft-com:office:spreadsheet}Index')
                if index_attr is not None:
                    target_idx = int(index_attr) - 1
                    while len(cells_data) < target_idx:
                        cells_data.append(None)
                
                data_el = c.find('.//ss:Data', namespaces)
                if data_el is not None:
                    cells_data.append(data_el.text)
                else:
                    cells_data.append(None)
            rows_data.append(cells_data)
            
        if not rows_data:
            continue
            
        # 对齐列长度
        max_len = max(len(row) for row in rows_data)
        for row in rows_data:
            while len(row) < max_len:
                row.append(None)
                
        # 处理表头与重复列名
        header = rows_data[0]
        seen = {}
        resolved_header = []
        for i, h in enumerate(header):
            if h is None or h == '':
                name = f"Unnamed: {i}"
            else:
                name = str(h).strip()
            if name in seen:
                seen[name] += 1
                name = f"{name}.{seen[name]}"
            else:
                seen[name] = 0
            resolved_header.append(name)
            
        df = pd.DataFrame(rows_data[1:], columns=resolved_header)
        
        # 自动尝试将数字类型的字符串转换为数值
        for col in df.columns:
            try:
                df[col] = pd.to_numeric(df[col])
            except (ValueError, TypeError):
                pass
                
        sheets_dict[sheet_name] = df
        
    return sheets_dict


def load_excel(file_path: str) -> Dict[str, pd.DataFrame]:
    """
    智能载入 Excel 文件，自动识别标准 Excel 与 XML Spreadsheet 2003。
    """
    is_xml_spreadsheet = False
    try:
        with open(file_path, 'rb') as f:
            start_bytes = f.read(100)
            if b'<?xml' in start_bytes:
                is_xml_spreadsheet = True
    except Exception:
        pass
        
    if is_xml_spreadsheet:
        return parse_xml_spreadsheet(file_path)
    else:
        xls = pd.ExcelFile(file_path)
        return {sheet: pd.read_excel(xls, sheet_name=sheet) for sheet in xls.sheet_names}
