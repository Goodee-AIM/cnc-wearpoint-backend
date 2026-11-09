from pathlib import Path

from diagrams import Cluster, Diagram, Edge
from diagrams.generic.database import SQL
from diagrams.generic.network import Firewall, Router, Subnet
from diagrams.generic.os import Ubuntu
from diagrams.generic.storage import Storage
from diagrams.onprem.client import User
from diagrams.onprem.network import Internet


OUTPUT_DIR = Path("docs/architecture/images")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

OUTPUT_FILE = OUTPUT_DIR / "cnc_wp_infrastructure"

graph_attr = {
    "fontsize": "18",
    "pad": "0.5",
    "nodesep": "0.7",
    "ranksep": "1.0",
}

with Diagram(
    "CNC WearPoint - NHN Cloud Infrastructure",
    filename=str(OUTPUT_FILE),
    outformat=["png", "svg"],
    show=False,
    direction="LR",
    graph_attr=graph_attr,
):
    team = User("Development Team")
    internet = Internet("Internet")

    floating_ip = Router("Floating IP")
    igw = Router("cnc-wp-igw")

    object_storage = Storage(
        "Object Storage\n"
        "Images / Model Artifacts\n"
        "(Planned)"
    )

    with Cluster("NHN Cloud - cnc-wp-vpc\n10.60.0.0/20"):

        with Cluster(
            "App Network\n"
            "cnc-wp-app-private\n"
            "10.60.0.64/27"
        ):
            app_sg = Firewall(
                "cnc-wp-app-sg\n"
                "SSH 22\n"
                "14.36.141.67/32"
            )

            app_vm = Ubuntu(
                "cnc-wp-app-01\n"
                "Ubuntu 24.04 LTS\n"
                "m2.c2m4\n"
                "2 vCPU / 4GB\n"
                "SSD 150GB"
            )

            app_rt = Router(
                "cnc-wp-app-rt\n"
                "10.60.0.0/20 → local\n"
                "0.0.0.0/0 → IGW"
            )

        with Cluster(
            "Database Network\n"
            "cnc-wp-db-private\n"
            "10.60.0.32/28"
        ):
            db_sg = Firewall(
                "cnc-wp-db-sg\n"
                "DB Port\n"
                "Source: App /27"
            )

            rds = SQL(
                "RDS for MySQL\n"
                "MySQL 8.4.6\n"
                "m2.c2m4\n"
                "General SSD 20GB"
            )

            private_rt = Router(
                "cnc-wp-private-rt\n"
                "Default Route Table\n"
                "10.60.0.0/20 → local\n"
                "No IGW"
            )

        with Cluster("Future Expansion"):
            gpu_vm = Ubuntu(
                "GPU Integration Server\n"
                "T4 GPU\n"
                "Model Inference"
            )

            nks = Subnet(
                "NKS Worker Network\n"
                "10.60.4.0/22\n"
                "Kubeflow / Istio"
            )

            monitoring = Subnet(
                "Monitoring\n"
                "Prometheus / Grafana\n"
                "(Planned)"
            )

    team >> Edge(label="SSH 22") >> internet
    internet >> floating_ip >> app_sg >> app_vm

    app_vm >> app_rt >> igw >> internet

    app_vm >> Edge(label="MySQL DB Port") >> db_sg >> rds

    rds - Edge(
        label="Private only",
        style="dashed"
    ) - private_rt

    app_vm >> Edge(
        label="Images / Artifacts",
        style="dashed"
    ) >> object_storage

    app_vm >> Edge(
        label="Future internal API",
        style="dashed"
    ) >> gpu_vm

    app_vm >> Edge(
        label="Future migration",
        style="dashed"
    ) >> nks

    nks >> monitoring