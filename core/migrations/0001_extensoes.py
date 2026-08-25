from django.contrib.postgres.operations import BtreeGistExtension, TrigramExtension
from django.db import migrations


class Migration(migrations.Migration):
    """Extensões PostgreSQL. `btree_gist` é usado pela constraint EXCLUDE dos apontamentos (F2)
    e `pg_trgm` pela busca global. Sem dependências: `makemigrations` gera 0002_initial depois."""

    initial = True
    dependencies = []
    operations = [BtreeGistExtension(), TrigramExtension()]
