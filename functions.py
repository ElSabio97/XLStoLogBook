import pandas as pd
import io
import fitz
import os
import streamlit as st
import requests

COLUMNAS = [
    "Fecha", "Origen", "Salida", "Destino", "Llegada", "Fabricante",
    "Matrícula", "SE", "ME", "Tiempo multipiloto", "Tiempo total de vuelo",
    "Nombre del PIC", "Landings Día", "Landings Noche", "Noche", "IFR",
    "Piloto al mando", "Co-piloto", "Doble mando", "Instructor",
    "Fecha simu", "Tipo", "Total de sesión", "Observaciones", "datetime"
]

def read_new_file(new_file):
    renamed_name = new_file.name.replace(".xls", ".html")
    new_file.name = renamed_name
    file_nuevo = pd.read_html(new_file)
    df_nuevo = pd.DataFrame(file_nuevo[0]).iloc[:-2]
    df_nuevo.columns = COLUMNAS
    df_nuevo['datetime'] = pd.to_datetime(df_nuevo['Fecha'] + ' ' + df_nuevo['Salida'], format='%d/%m/%y %H:%M', errors='coerce')
    df_nuevo['datetime_simu'] = pd.to_datetime(df_nuevo['Fecha simu'], format='%d/%m/%y', errors='coerce')
    df_nuevo['datetime_simu'] += pd.to_timedelta(df_nuevo.groupby('Fecha simu').cumcount(), unit='m')
    df_nuevo['datetime'] = df_nuevo['datetime'].combine_first(df_nuevo['datetime_simu'])
    return df_nuevo.drop(columns=['datetime_simu'])

def rellenar_y_combinar_pdfs(entry_url, exit_file, data, start_page=0, start_row=0):
    # Descargar el archivo PDF desde la URL de GitHub
    response = requests.get(entry_url)
    if response.status_code != 200:
        st.error(f"No se pudo descargar la plantilla desde {entry_url}. Código de estado: {response.status_code}")
        raise FileNotFoundError(f"No se pudo descargar la plantilla desde {entry_url}")
    
    # Guardar temporalmente el archivo descargado
    temp_input_file = "temp_LogBook_Rellenable.pdf"
    with open(temp_input_file, "wb") as f:
        f.write(response.content)
    
    df = data
    
    # Drop first row if it contains the str "Fecha"
    if df.iloc[0, 0] == "Fecha":
        df = df.iloc[1:]
    
    # Replace any . to : except in column Nombre del PIC and Tipo
    df.loc[:, df.columns.difference(['Nombre del PIC', 'Tipo'])] = df.loc[:, df.columns.difference(['Nombre del PIC', 'Tipo'])].replace(r'\.', ':', regex=True)
    
    # Set a regex to replace all str after 'B737' in column 'Fabricante' but change it to 'B738'
    df['Fabricante'] = df['Fabricante'].str.replace(r'B737.*', 'B738', regex=True)
    
    df.drop(columns=["Remark", "datetime"], inplace=True, errors='ignore')

    # Calcular cuántas páginas lógicas son necesarias
    rows_per_logical_page = 14
    total_rows = len(df)
    total_logical_pages_needed = (total_rows + start_row + (rows_per_logical_page - 1)) // rows_per_logical_page
    
    # Crear una lista de DataFrames ajustada para respetar start_row
    dataframes = []
    for i in range(total_logical_pages_needed):
        start_idx = i * rows_per_logical_page - start_row
        end_idx = start_idx + rows_per_logical_page
        if start_idx < 0:
            empty_rows = min(-start_idx, rows_per_logical_page)
            empty_df = pd.DataFrame(index=range(empty_rows), columns=df.columns)
            if end_idx > 0:
                data_slice = df.iloc[:min(end_idx, total_rows)]
                combined_df = pd.concat([empty_df, data_slice]).reset_index(drop=True)
                dataframes.append(combined_df.iloc[:rows_per_logical_page])
            else:
                dataframes.append(empty_df.iloc[:rows_per_logical_page])
        else:
            if start_idx < total_rows:
                data_slice = df.iloc[start_idx:min(end_idx, total_rows)]
                if len(data_slice) < rows_per_logical_page:
                    empty_rows = rows_per_logical_page - len(data_slice)
                    empty_df = pd.DataFrame(index=range(empty_rows), columns=df.columns)
                    combined_df = pd.concat([data_slice, empty_df]).reset_index(drop=True)
                    dataframes.append(combined_df)
                else:
                    dataframes.append(data_slice)

    def time_to_minutes(time_str):
        """Convierte un string en formato HH:MM a minutos. Devuelve 0 si está vacío."""
        if pd.isna(time_str) or not time_str:
            return 0
        try:
            hours, minutes = map(int, str(time_str).split(":"))
            return hours * 60 + minutes
        except (ValueError, TypeError):
            return 0

    def minutes_to_time(minutes):
        """Convierte minutos a formato HH:MM."""
        hours = minutes // 60
        mins = minutes % 60
        return f"{hours:02d}:{mins:02d}"

    def process_pdf_widgets(input_path, output_pdf_path, dataframes, start_page):
        base_doc = fitz.open(input_path)
        widget_data = {}
        sum_columns = ["SE", "ME", "Tiempo multipiloto", "Tiempo total de vuelo", 
                       "Landings Día", "Landings Noche", "Noche", "IFR", "Piloto al mando", 
                       "Co-piloto", "Doble mando", "Instructor", "Total de sesión"]
        numeric_columns = ["Landings Día", "Landings Noche"]
        
        for page_num, page in enumerate(base_doc):
            widgets = page.widgets()
            if widgets:
                widget_data[page_num] = []
                for widget in widgets:
                    rect = widget.rect
                    field_name = widget.field_name or "default"
                    widget_data[page_num].append({
                        'coords': (rect.x0, rect.y0, rect.x1, rect.y1),
                        'field_name': field_name
                    })
                    page.delete_widget(widget)
        
        final_doc = fitz.open()
        pages_per_logical_page = 2
        
        for _ in range(start_page):
            final_doc.insert_pdf(base_doc, from_page=0, to_page=1)
        
        for _ in dataframes:
            final_doc.insert_pdf(base_doc, from_page=0, to_page=1)
        base_doc.close()
        
        def get_base_font_size(field_name):
            if "TOTAL DESDE LAS PÁGINAS PREVIAS SE" in field_name or "TOTAL DE ESTA PÁGINA SE" in field_name or "TIEMPO TOTAL SE" in field_name:
                return 6
            else:
                return 8
        
        def adjust_font_size(text, rect, max_font_size, font):
            target_width = rect.width * 0.9
            target_height = rect.height * 0.9
            low, high = 5, max_font_size
            optimal_size = low
            while low <= high:
                mid = (low + high) // 2
                text_width = font.text_length(str(text), fontsize=mid)
                text_height = mid * 1.2
                if text_width <= target_width and text_height <= target_height:
                    optimal_size = mid
                    low = mid + 1
                else:
                    high = mid - 1
            return optimal_size
        
        cumulative_totals = {col: 0 for col in sum_columns}
        font = fitz.Font("helv")
        
        for df_idx, df in enumerate(dataframes):
            df = df.replace("--", "")
            df_totals = {col: 0 for col in sum_columns}
            for col in sum_columns:
                if col in df.columns:
                    if col in numeric_columns:
                        df_totals[col] = sum(int(df[col].iloc[i]) if pd.notna(df[col].iloc[i]) and df[col].iloc[i] else 0 for i in range(len(df)))
                    else:
                        df_totals[col] = sum(time_to_minutes(df[col].iloc[i]) for i in range(len(df)))
            
            logical_page_start = start_page + df_idx
            start_page_idx = logical_page_start * pages_per_logical_page
            end_page_idx = start_page_idx + pages_per_logical_page
            
            for page_num in range(start_page_idx, min(end_page_idx, len(final_doc))):
                page = final_doc[page_num]
                base_page_num = page_num % pages_per_logical_page
                
                if base_page_num in widget_data:
                    widgets_list = widget_data[base_page_num]
                    
                    for widget in widgets_list:
                        x0, y0, x1, y1 = widget['coords']
                        field_name = widget['field_name']
                        rect = fitz.Rect(x0, y0, x1, y1)
                        
                        text = ""
                        
                        if field_name == "Número de página":
                            text = str(logical_page_start + 1)
                        
                        elif not any(x in field_name for x in ["TIEMPO TOTAL", "TOTAL DE ESTA PÁGINA", "TOTAL DESDE LAS PÁGINAS PREVIAS"]):
                            parts = field_name.split("_")
                            if len(parts) > 1 and parts[-1].isdigit():
                                row_idx = int(parts[-1])
                                if row_idx < len(df):
                                    row = df.iloc[row_idx]
                                    for col in df.columns:
                                        expected_prefix = f"{col.upper()}_"
                                        if col != "datetime" and field_name.upper().startswith(expected_prefix):
                                            text = str(row[col]) if pd.notna(row[col]) else ""
                                            if text == "0" or text == "00:00":
                                                text = ""
                                            break
                        
                        else:
                            col_name = None
                            total_type = None
                            for col in sum_columns:
                                if f"TIEMPO TOTAL {col.upper()}" == field_name.upper():
                                    col_name = col
                                    total_type = "TIEMPO TOTAL"
                                    break
                                elif f"TOTAL DE ESTA PÁGINA {col.upper()}" == field_name.upper():
                                    col_name = col
                                    total_type = "TOTAL DE ESTA PÁGINA"
                                    break
                                elif f"TOTAL DESDE LAS PÁGINAS PREVIAS {col.upper()}" == field_name.upper():
                                    col_name = col
                                    total_type = "TOTAL DESDE LAS PÁGINAS PREVIAS"
                                    break
                            
                            if col_name:
                                if total_type == "TIEMPO TOTAL":
                                    total = cumulative_totals[col_name] + df_totals[col_name]
                                    text = str(total) if col_name in numeric_columns else minutes_to_time(total)
                                    if text == "0" or text == "00:00":
                                        text = ""
                                elif total_type == "TOTAL DE ESTA PÁGINA":
                                    total = df_totals[col_name]
                                    text = str(total) if col_name in numeric_columns else minutes_to_time(total)
                                    if text == "0" or text == "00:00":
                                        text = ""
                                elif total_type == "TOTAL DESDE LAS PÁGINAS PREVIAS":
                                    total = cumulative_totals[col_name]
                                    text = str(total) if col_name in numeric_columns else minutes_to_time(total)
                                    if text == "0" or text == "00:00":
                                        text = ""
                        
                        max_font_size = get_base_font_size(field_name)
                        if "Nombre del PIC" in field_name or "Tipo" in field_name:
                            font_size = adjust_font_size(text, rect, min(8, max_font_size), font)
                            if font_size == 5 and font.text_length(text, fontsize=5) > rect.width * 0.9:
                                page.insert_textbox(rect, text, fontsize=5, fontname="helv", color=[0, 0, 0], align=fitz.TEXT_ALIGN_CENTER)
                            else:
                                text_width = font.text_length(text, fontsize=font_size)
                                text_height = font_size * 1.2
                                x_center = x0 + (rect.width - text_width) / 2
                                y_center = y0 + (rect.height - text_height) / 2 + text_height * 0.8
                                page.insert_text((x_center, y_center), text, fontsize=font_size, fontname="helv", color=[0, 0, 0])
                        else:
                            font_size = max_font_size
                            text_width = font.text_length(text, fontsize=font_size)
                            text_height = font_size * 1.2
                            x_center = x0 + (rect.width - text_width) / 2
                            y_center = y0 + (rect.height - text_height) / 2 + text_height * 0.8
                            page.insert_text((x_center, y_center), text, fontsize=font_size, fontname="helv", color=[0, 0, 0])
            
            for col in sum_columns:
                if col in df.columns:
                    cumulative_totals[col] += df_totals[col]

        final_doc.ez_save(output_pdf_path, garbage=3, clean=True)
        final_doc.close()
        
        # Limpiar archivo temporal
        if os.path.exists(input_path):
            os.remove(input_path)

    process_pdf_widgets(temp_input_file, exit_file, dataframes, start_page)
    return exit_file