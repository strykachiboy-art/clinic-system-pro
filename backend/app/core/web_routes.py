from flask import Blueprint, render_template


web_bp = Blueprint("web", __name__)

NAVIGATION_MODULES = [
    {"slug": "clinic", "label": "Clinic"},
    {"slug": "patient", "label": "Patients"},
    {"slug": "appointment", "label": "Appointments"},
    {"slug": "consultation", "label": "Consultations"},
    {"slug": "inventory", "label": "Inventory"},
    {"slug": "pharmacy", "label": "Pharmacy"},
    {"slug": "lab", "label": "Laboratory"},
    {"slug": "billing", "label": "Billing"},
    {"slug": "staff", "label": "Staff"},
    {"slug": "ward", "label": "Ward"},
    {"slug": "reports", "label": "Reports"},
]


@web_bp.app_context_processor
def inject_navigation():
    return {"navigation_modules": NAVIGATION_MODULES}


@web_bp.get("/")
def home():
    return render_template("dashboard/index.html", page_title="Dashboard")


@web_bp.get("/login")
def login():
    return render_template("auth/login.html", page_title="Sign in")


@web_bp.get("/dashboard")
def dashboard():
    return render_template("dashboard/index.html", page_title="Dashboard")


@web_bp.get("/<string:module>")
def module_index(module: str):
    return render_template(
        f"modules/{module}/index.html",
        page_title=module.replace("_", " ").title(),
    )
