import streamlit as st
import pandas as pd
import numpy as np
import pingouin as pg
import plotly.express as px
import plotly.graph_objects as go


def gen_anova_data(df, columns, groups_col):
    for col in columns:
        result = pg.anova(data=df, dv=col, between=groups_col, detailed=True).set_index(
            "Source"
        )
        p = result.loc[groups_col, "p-unc"]
        f = result.loc[groups_col, "F"]
        yield col, p, f


def add_bonferroni_to_anova(df):
    # add Bonferroni corrected p-values for multiple testing correction
    if "p_bonferroni" not in df.columns:
        df.insert(2, "p_bonferroni", pg.multicomp(df["p"], method="bonf")[1])
    # add significance
    if "significant" not in df.columns:
        df.insert(3, "significant", df["p_bonferroni"] < 0.05)
    # sort by p-value
    df.sort_values("p", inplace=True)
    return df


@st.cache_data
def anova(df, attribute):
    df = pd.DataFrame(
        np.fromiter(
            gen_anova_data(
                pd.concat([df, st.session_state.md], axis=1),
                df.columns,
                attribute,
            ),
            dtype=[("metabolite", "U100"), ("p", "f"), ("F", "f")],
        )
    )
    df = add_bonferroni_to_anova(df)
    return df


@st.cache_resource
def get_anova_plot(anova):
    # first plot insignificant features
    fig = px.scatter(
        x=anova[anova["significant"] == False]["F"].apply(np.log),
        y=anova[anova["significant"] == False]["p"].apply(lambda x: -np.log(x)),
        template="plotly_white",
        width=600,
        height=600,
    )
    fig.update_traces(marker_color="#696880")

    # plot significant features
    fig.add_scatter(
        x=anova[anova["significant"]]["F"].apply(np.log),
        y=anova[anova["significant"]]["p"].apply(lambda x: -np.log(x)),
        mode="markers+text",
        text=anova["metabolite"].iloc[:5],
        textposition="top left",
        textfont=dict(color="#ef553b", size=12),
        name="significant",
    )

    fig.update_layout(
        font={"color": "grey", "size": 12, "family": "Sans"},
        title={
            "text": f"ANOVA - {st.session_state.anova_attribute.upper()}",
            "font_color": "#3E3D53",
        },
        xaxis_title="log(F)",
        yaxis_title="-log(p)",
    )
    return fig


@st.cache_resource
def get_metabolite_boxplot(anova, metabolite):
    attribute = "ATTRIBUTE_"+st.session_state.anova_attribute
    p_value = anova.set_index("metabolite")._get_value(metabolite, "p")
    df = pd.concat([st.session_state.data, st.session_state.md], axis=1)[
        [attribute, metabolite]
    ]
    title = f"{metabolite}<br>p-value: {p_value}"
    fig = px.box(
        df,
        x=attribute,
        y=metabolite,
        template="plotly_white",
        width=800,
        height=600,
        points="all",
        color=attribute,
    )

    fig.update_layout(
        font={"color": "grey", "size": 12, "family": "Sans"},
        title={"text": title, "font_color": "#3E3D53"},
        xaxis_title=attribute.replace("ATTRIBUTE_", ""),
        yaxis_title="intensity",
    )
    return fig


def gen_pairwise_tukey(df, metabolites, attribute):
    """Yield results for pairwise Tukey test for all metabolites between two options within the attribute."""
    for metabolite in metabolites:
        tukey = pg.pairwise_tukey(df, dv=metabolite, between=attribute)
        yield (
            metabolite,
            tukey.loc[0, "diff"],
            tukey.loc[0, "p-tukey"],
            attribute.replace("ATTRIBUTE_", ""),
            tukey.loc[0, "A"],
            tukey.loc[0, "B"],
            tukey.loc[0, "mean(A)"],
            tukey.loc[0, "mean(B)"],
        )


def add_bonferroni_to_tukeys(tukey):
    if "stats_p_bonferroni" not in tukey.columns:
        # add Bonferroni corrected p-values
        tukey.insert(
            3, "stats_p_bonferroni", pg.multicomp(tukey["stats_p"], method="bonf")[1]
        )
        # add significance
        tukey.insert(4, "stats_significant", tukey["stats_p_bonferroni"] < 0.05)
        # sort by p-value
        tukey.sort_values("stats_p", inplace=True)
    return tukey


@st.cache_data
def tukey(df, attribute, elements):
    significant_metabolites = df[df["significant"]]["metabolite"]
    data = pd.concat(
        [
            st.session_state.data.loc[:, significant_metabolites],
            st.session_state.md.loc[:, attribute],
        ],
        axis=1,
    )
    data = data[data[attribute].isin(elements)]
    tukey = pd.DataFrame(
        np.fromiter(
            gen_pairwise_tukey(data, significant_metabolites, attribute),
            dtype=[
                ("stats_metabolite", "U100"),
                (f"diff", "f"),
                ("stats_p", "f"),
                ("attribute", "U100"),
                ("A", "U100"),
                ("B", "U100"),
                ("mean(A)", "f"),
                ("mean(B)", "f"),
            ],
        )
    )
    tukey = add_bonferroni_to_tukeys(tukey)
    return tukey


@st.cache_resource
def get_tukey_volcano_plot(df):
    # create figure
    fig = px.scatter(template="plotly_white")

    # plot insignificant values
    fig.add_trace(
        go.Scatter(
            x=df[df["stats_significant"] == False]["diff"],
            y=df[df["stats_significant"] == False]["stats_p"].apply(
                lambda x: -np.log(x)
            ),
            mode="markers",
            marker_color="#696880",
            name="insignificant",
        )
    )

    # plot significant values
    fig.add_trace(
        go.Scatter(
            x=df[df["stats_significant"]]["diff"],
            y=df[df["stats_significant"]]["stats_p"].apply(lambda x: -np.log(x)),
            mode="markers+text",
            text=df["stats_metabolite"].iloc[:5],
            textposition="top right",
            textfont=dict(color="#ef553b", size=12),
            marker_color="#ef553b",
            name="significant",
        )
    )

    fig.update_layout(
        font={"color": "grey", "size": 12, "family": "Sans"},
        title={
            "text": f"TUKEY - {st.session_state.anova_attribute.upper()}: {st.session_state.tukey_elements[0]} - {st.session_state.tukey_elements[1]}",
            "font_color": "#3E3D53",
        },
        xaxis_title=f"diff",
        yaxis_title="-log(p)",
    )
    return fig
