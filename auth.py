import streamlit as st

# Jerarquía de roles (de menor a mayor privilegio)
ROLE_HIERARCHY = {"user": 1, "admin": 2, "dev": 3}


def check_login():
    """Verifica si el usuario está autenticado. Si no, muestra el formulario de login."""
    if "authenticated" not in st.session_state:
        st.session_state.authenticated = False

    if st.session_state.authenticated:
        return True

    credentials = st.secrets["credentials"]
    roles = st.secrets["roles"]

    st.set_page_config(page_title="Login", page_icon="🔒", layout="centered")

    st.title("Sistema ERP")

    st.markdown("## 🔐 Login")
    username = st.text_input("Usuario")
    password = st.text_input("Contraseña", type="password")

    if st.button("Ingresar", type="primary", use_container_width=True):
        if username in credentials and credentials[username] == password:
            st.session_state.authenticated = True
            st.session_state.user = username
            st.session_state.role = roles.get(username, "user")
            st.success("Bienvenido")
            st.rerun()
        else:
            st.error("Usuario o contraseña incorrectos")

    return False


def get_role():
    """Retorna el rol del usuario actual."""
    return st.session_state.get("role", "user")


def get_role_level():
    """Retorna el nivel numérico del rol actual (1=user, 2=admin, 3=dev)."""
    return ROLE_HIERARCHY.get(get_role(), 1)


def require_role(allowed_roles):
    """
    Bloquea el acceso a la página si el usuario no tiene uno de los roles permitidos.

    Uso:
        require_role(["admin", "dev"])   # Solo admin y dev pueden acceder
        require_role(["dev"])            # Solo dev puede acceder
    """
    current_role = get_role()
    if current_role not in allowed_roles:
        st.error("⛔ No tienes permisos para acceder a esta sección.")
        st.info(f"Tu rol actual es **{current_role}**. Se requiere: {', '.join(allowed_roles)}.")
        st.stop()


def require_min_role(min_role):
    """
    Bloquea el acceso si el nivel del usuario es menor al rol mínimo requerido.

    Uso:
        require_min_role("admin")  # admin y dev pueden acceder
        require_min_role("dev")    # solo dev puede acceder
    """
    current_level = get_role_level()
    required_level = ROLE_HIERARCHY.get(min_role, 1)
    if current_level < required_level:
        current_role = get_role()
        st.error("⛔ No tienes permisos para acceder a esta sección.")
        st.info(f"Tu rol actual es **{current_role}**. Se requiere mínimo: **{min_role}**.")
        st.stop()


def role_badge():
    """Retorna un emoji + texto bonito para mostrar el rol en la UI."""
    badges = {
        "user": "👤 Usuario",
        "admin": "🛡️ Admin",
        "dev": "⚙️ Dev",
    }
    return badges.get(get_role(), "👤 Usuario")
