import click

from exceptions import CityError
from metro_parser.metro_parser import parser


@click.group()
def cli():
    pass


@cli.command()
@click.argument('city')
def parse_data(city):
    """Парсинг данных для указанного города."""
    try:
        parser.parse_data(city)
    except CityError as e:
        click.echo(f'Ошибка: {e}')


@cli.command()
def info():
    """Показать список доступных городов."""
    click.echo("Доступные города:")
    click.echo(list(parser.stores_info))


if __name__ == '__main__':
    cli()
