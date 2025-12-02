import marimo

__generated_with = "0.14.17"
app = marimo.App(width="medium", app_title="EAVS Data Explorer")


@app.cell
def _(mo):
    mo.md(
        r"""
    # EAVS Data Explorer

    This is a proof-of-concept using Marimo to export a deployable dashboard. It generates static HTML with WASM for data-loading and interactivity, and can be deployed with a static site host like GitHub pages. 
    """
    )
    return


@app.cell
def _():
    import marimo as mo
    import polars as pl
    import plotly.express as px
    return mo, pl, px


@app.cell
def _(mo):
    data_path = mo.notebook_location() / "public" / "data" / "combined.csv"
    return (data_path,)


@app.cell
def _(data_path, pl):
    df = pl.read_csv(str(data_path))
    return (df,)


@app.cell
def _():
    return


@app.cell
def _(df):
    dimensions = (
        "year",
        "fips_code",
        "jurisdiction_name",
        "state",
        "state_abbr",
    )

    measures = tuple(
        col for col, dtype in zip(df.columns, df.dtypes)
        if dtype.is_numeric() and col not in dimensions
    )

    years = df.select("year").unique().to_series().to_list()
    return dimensions, measures, years


@app.cell
def _(measures, mo, years):
    year_dropdown = mo.ui.dropdown(options=years, label="Year", value=years[0])
    yvar_dropdown = mo.ui.dropdown(options=measures, label="Y Variable", value=measures[0])
    xvar_dropdown = mo.ui.dropdown(options=measures, label="X Variable", value=measures[1])
    controls = mo.vstack([year_dropdown, yvar_dropdown, xvar_dropdown], justify="center")
    return controls, xvar_dropdown, year_dropdown, yvar_dropdown


@app.cell
def _(df, dimensions, pl, px, xvar_dropdown, year_dropdown, yvar_dropdown):
    plot = px.scatter(
        df.filter(pl.col("year")==year_dropdown.value), 
        x=xvar_dropdown.value, 
        y=yvar_dropdown.value, 
        hover_data=dimensions
    )

    return (plot,)


@app.cell
def _(controls, mo, plot):
    mo.hstack([controls, plot])
    return


@app.cell
def _(df, mo):
    mo.ui.dataframe(df)
    return


if __name__ == "__main__":
    app.run()
