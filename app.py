import streamlit as st
from functions import (rellenar_y_combinar_pdfs, read_new_file)
import pandas as pd

def main():
    st.title("LogBook Converter")

    # Código de verificación de Google AdSense
    st.markdown("""
    <script async src="https://pagead2.googlesyndication.com/pagead/js/adsbygoogle.js?client=ca-pub-9397947416042281" crossorigin="anonymous"></script>
    """, unsafe_allow_html=True)
    
    st.write("Sube tu archivo XLS para convertirlo a un PDF rellenado.")
    
    # Subida del archivo XLS
    file_uploader = st.file_uploader("Sube tu archivo XLS", type="xls", label_visibility="hidden")
    
    # Campos para página lógica y fila inicial
    start_page = st.number_input("Página lógica inicial del PDF (empezando en 1)", min_value=1, value=1)
    start_row = st.number_input("Fila inicial en la página lógica (empezando en 1)", min_value=1, value=1)
    
    if st.button("Convertir a PDF") and file_uploader is not None:
        # Leer el archivo XLS subido
        df_nuevo = read_new_file(file_uploader)
        if df_nuevo is None or len(df_nuevo) < 1:
            st.write("El archivo está vacío o no se pudo procesar.")
        else:
            # Generar el PDF usando la URL de GitHub
            pdf_path = rellenar_y_combinar_pdfs(
                "https://raw.githubusercontent.com/ElSabio97/XLStoLogBook/main/LogBook_Rellenable.pdf",  # Reemplaza con tu URL
                "LogBook_Rellenado.pdf", 
                df_nuevo, 
                start_page - 1, 
                start_row - 1
            )
            with open(pdf_path, "rb") as pdf_file:
                pdf_data = pdf_file.read()

            # Botón de descarga
            if st.download_button(
                label="Descargar LogBook",
                data=pdf_data,
                file_name="LogBook.pdf",
                mime="application/pdf"
            ):
                st.write("¡LogBook descargado!")

if __name__ == "__main__":
    main()
