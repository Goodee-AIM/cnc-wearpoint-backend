import base64
import mimetypes
import re
from pathlib import Path

from diagrams import Cluster, Diagram, Edge
from diagrams.generic.database import SQL
from diagrams.generic.network import Firewall, Router
from diagrams.generic.storage import Storage
from diagrams.onprem.client import User
from diagrams.onprem.container import Docker
from diagrams.onprem.mlops import Mlflow
from diagrams.onprem.network import Internet, Nginx


# ============================================================
# Output path
# ============================================================

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent.parent.parent

OUTPUT_DIR = PROJECT_ROOT / "docs" / "architecture" / "images"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

OUTPUT_NAME = "cnc_wp_infrastructure"
OUTPUT_PATH = OUTPUT_DIR / OUTPUT_NAME


# ============================================================
# SVG post-processing
# ============================================================

def embed_svg_images(svg_path: Path) -> None:
    """
    Convert local image references inside SVG into Base64 data URIs
    so the SVG renders correctly on GitHub and other environments.
    """

    if not svg_path.exists():
        print(f"[WARN] SVG not found: {svg_path}")
        return

    content = svg_path.read_text(encoding="utf-8")
    pattern = r'(?:xlink:href|href)="([^"]+)"'

    embedded_count = 0

    def replace_href(match):
        nonlocal embedded_count

        full_match = match.group(0)
        href = match.group(1)

        if href.startswith("data:"):
            return full_match

        image_path = Path(href)

        if not image_path.exists():
            return full_match

        mime_type, _ = mimetypes.guess_type(image_path.name)

        if mime_type is None:
            mime_type = "image/png"

        encoded = base64.b64encode(
            image_path.read_bytes()
        ).decode("ascii")

        embedded_count += 1
        attribute_name = full_match.split("=", 1)[0]

        return (
            f'{attribute_name}="data:{mime_type};base64,{encoded}"'
        )

    updated = re.sub(pattern, replace_href, content)
    svg_path.write_text(updated, encoding="utf-8")

    print(
        f"[OK] Embedded {embedded_count} SVG image(s): "
        f"{svg_path}"
    )


# ============================================================
# Graph style
# ============================================================

graph_attr = {
    "fontsize": "18",
    "pad": "0.5",
    "nodesep": "0.65",
    "ranksep": "1.0",
    "splines": "spline",
}

edge_attr = {
    "fontsize": "11",
}


# ============================================================
# Infrastructure diagram
# ============================================================

with Diagram(
    "CNC WearPoint - NHN Cloud Infrastructure",
    filename=str(OUTPUT_PATH),
    outformat=["png", "svg"],
    show=False,
    direction="LR",
    graph_attr=graph_attr,
    edge_attr=edge_attr,
):

    # ========================================================
    # External access
    # ========================================================

    web_user = User(
        "Web User\n"
        "https://aimw.duckdns.org"
    )

    admin = User(
        "Admin / Team\n"
        "SSH Management"
    )

    internet = Internet("Internet")

    floating_ip = Router(
        "Floating IP\n"
        "DuckDNS Target"
    )

    # ========================================================
    # NHN Cloud
    # ========================================================

    with Cluster("NHN Cloud"):

        # ----------------------------------------------------
        # VPC
        # ----------------------------------------------------

        with Cluster("cnc-wp-vpc\n10.60.0.0/20"):

            # =================================================
            # App Network
            # =================================================

            with Cluster(
                "App Network\n"
                "cnc-wp-app-private\n"
                "10.60.0.64/27"
            ):

                app_sg = Firewall(
                    "cnc-wp-app-sg\n"
                    "HTTP 80 / HTTPS 443\n"
                    "SSH 22\n"
                    "SSH Source: 14.36.141.67/32"
                )

                app_rt = Router(
                    "cnc-wp-app-rt\n"
                    "10.60.0.0/20 -> local\n"
                    "0.0.0.0/0 -> IGW"
                )

                igw = Router("cnc-wp-igw")

                with Cluster(
                    "cnc-wp-app-01\n"
                    "Ubuntu 24.04 LTS\n"
                    "m2.c2m4 | 2 vCPU / 4GB\n"
                    "SSD 150GB"
                ):

                    nginx = Nginx(
                        "Host Nginx\n"
                        "HTTPS 443\n"
                        "HTTP 80 -> 443\n"
                        "Let's Encrypt"
                    )

                    frontend = Docker(
                        "Frontend\n"
                        "React + Nginx\n"
                        "127.0.0.1:8080"
                    )

                    backend = Docker(
                        "Backend\n"
                        "FastAPI\n"
                        "127.0.0.1:8000"
                    )

                    mlflow = Mlflow(
                        "MLflow 3.18.0\n"
                        "systemd / venv\n"
                        "127.0.0.1:5000"
                    )

            # =================================================
            # Database Network
            # =================================================

            with Cluster(
                "Database Network\n"
                "cnc-wp-db-private\n"
                "10.60.0.32/28"
            ):

                db_sg = Firewall(
                    "cnc-wp-db-sg\n"
                    "MySQL 3306\n"
                    "Source: App Subnet\n"
                    "10.60.0.64/27"
                )

                rds = SQL(
                    "RDS for MySQL\n"
                    "MySQL 8.4.6\n"
                    "m2.c2m4 | SSD 20GB\n\n"
                    "cnc_wearpoint\n"
                    "mlflow\n"
                    "mlflow_auth"
                )

                private_rt = Router(
                    "cnc-wp-private-rt\n"
                    "10.60.0.0/20 -> local\n"
                    "No IGW"
                )

        # ----------------------------------------------------
        # NHN Managed Storage
        # Object Storage is not placed inside the VPC subnet.
        # ----------------------------------------------------

        object_storage = Storage(
            "NHN Object Storage\n"
            "PRIVATE / Standard\n\n"
            "cnc-wearpoint-data\n"
            "cnc-wearpoint-mlflow"
        )

    # ========================================================
    # Public service access
    # ========================================================

    web_user >> Edge(
        label="HTTPS 443"
    ) >> internet

    internet >> Edge(
        label="DNS -> Floating IP"
    ) >> floating_ip

    floating_ip >> Edge(
        label="80 / 443"
    ) >> app_sg

    app_sg >> Edge(
        label="Web Traffic"
    ) >> nginx

    # ========================================================
    # Administrative access
    # ========================================================

    admin >> Edge(
        label="SSH 22\n14.36.141.67/32",
        style="dashed",
        color="#7b8894",
    ) >> floating_ip

    app_sg >> Edge(
        label="SSH 22",
        style="dashed",
        color="#7b8894",
    ) >> backend

    # ========================================================
    # Nginx routing
    # ========================================================

    nginx >> Edge(
        label="/"
    ) >> frontend

    nginx >> Edge(
        label="/api/"
    ) >> backend

    nginx >> Edge(
        label="/mlflow/"
    ) >> mlflow

    # ========================================================
    # RDS access
    # ========================================================

    backend >> Edge(
        label="MySQL 3306\nTLS 1.3 + CA",
        color="#2b6cb0",
    ) >> db_sg

    mlflow >> Edge(
        label="MySQL 3306\nTLS 1.3 + CA",
        color="#2b6cb0",
    ) >> db_sg

    db_sg >> rds

    # ========================================================
    # Object Storage access
    # ========================================================

    backend >> Edge(
        label="HTTPS 443 / S3 API\nimages + sensors",
        color="#dd6b20",
    ) >> object_storage

    mlflow >> Edge(
        label="HTTPS 443 / S3 API\nMLflow artifacts",
        color="#dd6b20",
    ) >> object_storage

    # ========================================================
    # Route table relationships
    # Supporting configuration, not application traffic.
    # ========================================================

    nginx >> Edge(
        label="App subnet route",
        style="dashed",
        color="#7b8894",
    ) >> app_rt

    app_rt >> Edge(
        label="default route",
        style="dashed",
        color="#7b8894",
    ) >> igw

    rds >> Edge(
        label="DB subnet route",
        style="dashed",
        color="#7b8894",
    ) >> private_rt


# ============================================================
# Post-process SVG
# ============================================================

SVG_FILE = OUTPUT_DIR / f"{OUTPUT_NAME}.svg"
embed_svg_images(SVG_FILE)