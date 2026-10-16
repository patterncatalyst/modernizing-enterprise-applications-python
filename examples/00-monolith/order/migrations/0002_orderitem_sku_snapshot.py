# r04/ch.19: OrderItem.inventory_item (the cross-context FK, SMELL[ch.18])
# is replaced by a denormalized sku/item_name snapshot (unit_price_cents was
# already a snapshot column). Operation order matters: ADD the new columns,
# BACKFILL them from the still-live FK, THEN drop the FK -- never the other
# way around, or the backfill would have nothing left to read from.

from django.db import migrations, models


def backfill_sku_and_item_name(apps, schema_editor):
    OrderItem = apps.get_model("order", "OrderItem")
    # Historical-model queryset -- select_related keeps this a single query
    # per batch rather than one inventory_items lookup per row.
    for item in OrderItem.objects.select_related("inventory_item").all():
        item.sku = item.inventory_item.sku
        item.item_name = item.inventory_item.name
        item.save(update_fields=["sku", "item_name"])


class Migration(migrations.Migration):
    dependencies = [
        ("order", "0001_initial"),
        ("inventory", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="orderitem",
            name="sku",
            field=models.CharField(default="", max_length=64),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name="orderitem",
            name="item_name",
            field=models.CharField(default="", max_length=255),
            preserve_default=False,
        ),
        migrations.RunPython(backfill_sku_and_item_name, migrations.RunPython.noop),
        migrations.RemoveField(
            model_name="orderitem",
            name="inventory_item",
        ),
    ]
