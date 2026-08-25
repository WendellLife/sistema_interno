from rest_framework.pagination import CursorPagination


class PaginacaoPadrao(CursorPagination):
    page_size = 50
    ordering = "-criado_em"
    cursor_query_param = "cursor"
