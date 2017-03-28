"""
Create summary statistics / plots for runs from
evcouplings app

Authors:
  Thomas A. Hopf
"""

# chose backend for command-line usage
import matplotlib
matplotlib.use("Agg")

from collections import defaultdict
import filelock

import pandas as pd
import click
import matplotlib.pyplot as plt

from evcouplings.utils.system import valid_file
from evcouplings.utils.config import read_config_file, InvalidParameterError

CONTEXT_SETTINGS = dict(help_option_names=['-h', '--help'])


def protein_monomer(prefix, configs):
    """
    Create results summary for run using
    protein_monomer pipeline

    # TODO
    """
    MIN_SEQ_DIST = 6
    MIN_PROBABILITY = 0.9

    ali_table = pd.DataFrame()
    prefix_to_cfgs = {}
    data = defaultdict(lambda: defaultdict())

    # go through all config files
    for cfg_file in configs:
        # check if the file exists and has contents
        # since run might not yet have finished or crashed
        if valid_file(cfg_file):
            # job input configuration
            C = read_config_file(cfg_file)
            sub_prefix = C["global"]["prefix"]
            domain_threshold = C["align"]["domain_threshold"]
            sub_index = (domain_threshold, sub_prefix)

            final_state_cfg = sub_prefix + "_final_global_state.outcfg"
            if not valid_file(final_state_cfg):
                continue

            # read final output state of job
            R = read_config_file(final_state_cfg)
            data[sub_index]["identities"] = R["identities_file"]
            data[sub_index]["frequencies"] = R["frequencies_file"]
            data[sub_index]["minimum_column_coverage"] = C["align"]["minimum_column_coverage"]

            stat_file = R["statistics_file"]
            ec_file = R.get("ec_file", "")
            ec_comp_file = R.get("ec_compared_longrange_file", "")

            prefix_to_cfgs[(sub_prefix)] = (C, R)

            # read and modify alignment statistics
            if valid_file(stat_file):
                # get alignment stats for current job
                stat_df = pd.read_csv(stat_file)
                n_eff = R["effective_sequences"]

                if n_eff is not None:
                    stat_df.loc[0, "N_eff"] = n_eff

                stat_df.loc[0, "domain_threshold"] = domain_threshold
                L = stat_df.loc[0, "num_cov"]

                # try to get number of significant ECs in addition
                if valid_file(ec_file):
                    ecs = pd.read_csv(ec_file)
                    num_sig = len(ecs.query(
                        "abs(i-j) >= @MIN_SEQ_DIST and probability >= @MIN_PROBABILITY"
                    ))
                    stat_df.loc[0, "num_significant"] = num_sig

                # try to get EC precision in addition
                if valid_file(ec_comp_file):
                    ec_comp = pd.read_csv(ec_comp_file)
                    stat_df.loc[0, "precision"] = ec_comp.iloc[L]["precision"]

                # finally, append to global table
                ali_table = ali_table.append(stat_df)

    # sort table by sequence search threshold
    ali_table = ali_table.sort_values(by="domain_threshold")

    # when saving files, have to aquire lock to make sure
    # jobs don't start overwriting results

    # make plots and save
    fig = _protein_monomer_plot(ali_table, data)
    plot_file = prefix + "_job_statistics_summary.pdf"
    lock_plot = filelock.FileLock(plot_file)
    with lock_plot:
        fig.savefig(plot_file, bbox_inches="tight")

    # save ali statistics table
    table_file = prefix + "_job_statistics_summary.csv"
    lock_table = filelock.FileLock(table_file)
    with lock_table:
        ali_table.to_csv(
            table_file, index=False, float_format="%.3f"
        )

    return ali_table


def _protein_monomer_plot(ali_table, data):
    """
    # TODO
    """
    import seaborn as sns
    sns.set_palette("Paired", len(ali_table), None)

    FONTSIZE = 16
    # set up plot and grid
    fig = plt.figure(figsize=(15, 15))
    gridsize = ((3, 2))
    ax_cov = plt.subplot2grid(gridsize, (0, 0), colspan=1)
    ax_distr = plt.subplot2grid(gridsize, (0, 1), colspan=1)
    ax_gaps = plt.subplot2grid(gridsize, (1, 0), colspan=2)
    ax_sig = plt.subplot2grid(gridsize, (2, 0), colspan=1)
    ax_comp = plt.subplot2grid(gridsize, (2, 1), colspan=1)

    # 1) Number of sequences, coverage
    l_seqs = ax_cov.plot(
        ali_table.domain_threshold, ali_table.N_eff / ali_table.num_cov,
        "ok-", label="# Sequences"
    )
    ax_cov.set_xlabel("Domain inclusion threshold")
    ax_cov.set_ylabel("# effective sequences / L")
    ax_cov.set_title("Sequences and coverage", fontsize=FONTSIZE)
    ax_cov.legend(loc="lower left")

    ax_cov2 = ax_cov.twinx()
    l_cov = ax_cov2.plot(
        ali_table.domain_threshold, ali_table.num_cov / ali_table.seqlen,
        "o-", label="Coverage", color="#2079b4"
    )
    ax_cov2.set_ylabel("Coverage (% of region)")
    ax_cov2.legend(loc="lower right")
    ax_cov2.set_ylim(0, 1)

    # 2) sequence identity & coverage distributions
    for (domain_threshold, subjob), subdata in sorted(data.items()):
        # sequence identities to query
        if valid_file(subdata["identities"]):
            ids = pd.read_csv(subdata["identities"]).identity_to_query.dropna()
            ax_distr.hist(
                ids, histtype="step", range=(0, 1.0),
                bins=100, normed=True, cumulative=True, linewidth=3,
                label=str(domain_threshold)
            )

            ali_table.loc[ali_table.prefix == subjob, "average_identity"] = ids.mean()

        # coverage distribution
        if valid_file(subdata["frequencies"]):
            freqs = pd.read_csv(subdata["frequencies"])
            # print(freqs.head())
            ax_gaps.plot(
                freqs.pos, 1 - freqs.loc[:, "-"], "o", linewidth=3,
                label=str(domain_threshold)
            )
            mincov = subdata["minimum_column_coverage"]
            if mincov > 1:
                mincov /= 100

            ax_gaps.axhline(mincov, ls="--", color="k")

    ax_distr.set_xlabel("% sequence identity to query")
    ax_distr.set_title("Sequence identity distribution", fontsize=FONTSIZE)
    ax_distr.set_xlim(0, 1)
    ax_distr.set_ylim(0, 1)
    ax_distr.legend()

    ax_gaps.set_title("Gap statistics", fontsize=FONTSIZE)
    ax_gaps.set_xlabel("Sequence index")
    ax_gaps.set_ylabel("Column coverage (1 - % gaps)")
    ax_gaps.autoscale(enable=True, axis='x', tight=True)
    ax_gaps.set_ylim(0, 1)
    ax_gaps.legend(loc="best")

    # number of significant ECs, EC precision
    if "num_significant" in ali_table.columns:
        ax_sig.plot(
            ali_table.domain_threshold,
            ali_table.num_significant / ali_table.num_cov,
            "ok-"
        )

    ax_sig.set_title("Significant ECs", fontsize=FONTSIZE)
    ax_sig.set_xlabel("Domain inclusion threshold")
    ax_sig.set_ylabel("Fraction of significant ECs (% of L)")

    if "precision" in ali_table.columns:
        ax_comp.plot(ali_table.domain_threshold, ali_table.precision, "ok-")

    ax_comp.set_title("Comparison to 3D (top L ECs)", fontsize=FONTSIZE)
    ax_comp.set_xlabel("Domain inclusion threshold")
    ax_comp.set_ylabel("EC precision")
    ax_comp.set_ylim(0, 1)

    return fig


def protein_complex(prefix, configs):
    """
    Create results summary for run using
    protein_complex pipeline

    # TODO
    """
    raise NotImplementedError(
        "EVcomplex summary not yet implemented."
    )


PIPELINE_TO_SUMMARIZER = {
    "protein_monomer": protein_monomer,
    "protein_complex": protein_complex,
}


@click.command(context_settings=CONTEXT_SETTINGS)
# run settings
@click.argument('pipeline', nargs=1, required=True)
@click.argument('prefix', nargs=1, required=True)
@click.argument('configs', nargs=-1)
def run(**kwargs):
    """
    Create summary statistics for evcouplings pipeline runs
    """
    try:
        summarizer = PIPELINE_TO_SUMMARIZER[kwargs["pipeline"]]
    except KeyError:
        raise InvalidParameterError(
            "Not a valid pipeline, valid selections are: {}".format(
                ",".join(PIPELINE_TO_SUMMARIZER.keys())
            )
        )

    summarizer(kwargs["prefix"], kwargs["configs"])


if __name__ == '__main__':
    run()
