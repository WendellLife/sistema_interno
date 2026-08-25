from django.db import migrations

SQL_CRIAR = r"""
CREATE OR REPLACE FUNCTION proximo_numero(prefixo text, ano int) RETURNS text AS $$
DECLARE
  seq text := format('seq_numero_%s_%s', lower(prefixo), ano);
  v bigint;
BEGIN
  BEGIN
    EXECUTE format('CREATE SEQUENCE IF NOT EXISTS %I', seq);
  EXCEPTION WHEN duplicate_table OR unique_violation THEN
    NULL;  -- outra transação criou a sequência ao mesmo tempo
  END;
  EXECUTE format('SELECT nextval(%L)', seq) INTO v;
  RETURN format('%s-%s-%s', upper(prefixo), ano, lpad(v::text, 4, '0'));
END
$$ LANGUAGE plpgsql;
"""

SQL_REMOVER = "DROP FUNCTION IF EXISTS proximo_numero(text, int);"


class Migration(migrations.Migration):
    """Numeração `TI-2026-0341` / `SOL-2026-0912` vem de sequência do PostgreSQL, nunca de count()+1."""

    dependencies = [("core", "0001_extensoes")]
    operations = [migrations.RunSQL(SQL_CRIAR, SQL_REMOVER)]
