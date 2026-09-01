from django import forms

from chamados.models import Categoria, Chamado


class NovoChamadoForm(forms.Form):
    titulo = forms.CharField(max_length=180)
    descricao = forms.CharField(widget=forms.Textarea)
    categoria = forms.ModelChoiceField(queryset=Categoria.objects.all())
    prioridade = forms.ChoiceField(choices=Chamado.Prioridade.choices, initial="media")


class LancamentoManualForm(forms.Form):
    tipo = forms.IntegerField()
    data = forms.DateField()  # type: ignore[assignment]  # a metaclasse move para declared_fields
    inicio = forms.TimeField()
    fim = forms.TimeField()
    observacao = forms.CharField(max_length=240, required=False)
    motivo_retrabalho = forms.IntegerField(required=False)
    detalhe_retrabalho = forms.CharField(max_length=240, required=False)


class ComentarioForm(forms.Form):
    texto = forms.CharField(widget=forms.Textarea)
    interno = forms.BooleanField(required=False)
