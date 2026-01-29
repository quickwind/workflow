import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0003_workflow_definitions"),
    ]

    operations = [
        migrations.CreateModel(
            name="WorkflowInstance",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("running", "Running"),
                            ("waiting", "Waiting"),
                            ("completed", "Completed"),
                            ("failed", "Failed"),
                        ],
                        default="running",
                        max_length=20,
                    ),
                ),
                ("correlation_id", models.CharField(blank=True, max_length=200)),
                ("business_key", models.CharField(blank=True, max_length=200)),
                ("serialized_state", models.JSONField(default=dict)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "definition_version",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="instances",
                        to="core.workflowdefinitionversion",
                    ),
                ),
                (
                    "tenant",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="%(class)ss",
                        to="core.tenant",
                    ),
                ),
            ],
            options={
                "abstract": False,
            },
        ),
    ]
