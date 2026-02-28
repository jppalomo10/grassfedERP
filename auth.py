import streamlit as st


def check_login():
    if "authenticated" not in st.session_state:
        st.session_state.authenticated = False

    if st.session_state.authenticated:
        return True

    credentials = st.secrets["credentials"]

    col1, col2, col3 = st.columns(3)
    col3.image(
        "https://www.ufm.edu/wp-content/uploads/2023/04/logo-ufm01.png",
        width=180
    )

    col1.markdown(
        "<h2 style='text-align: center;'>Sistema ERP</h2>",
        unsafe_allow_html=True
    )

    st.markdown("## 🔐 Login")
    username = st.text_input("Usuario")
    password = st.text_input("Contraseña", type="password")

    if st.button("Ingresar", type="primary", use_container_width=True):
        if username in credentials and credentials[username] == password:
            st.session_state.authenticated = True
            st.session_state.user = username
            st.success("Bienvenido")
            st.rerun()
        else:
            st.error("Usuario o contraseña incorrectos")

    return False
