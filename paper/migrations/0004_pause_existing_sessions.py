from django.db import migrations


def pause_existing(apps, schema_editor):
    apps.get_model("paper", "PaperSession").objects.update(active=False, scheduled=False, state="paused")


class Migration(migrations.Migration):
    dependencies = [("paper", "0003_accountcycle_accountorder_accountpolicy_and_more")]
    operations = [migrations.RunPython(pause_existing, migrations.RunPython.noop)]
