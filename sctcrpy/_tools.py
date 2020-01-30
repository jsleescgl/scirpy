import itertools
import parasail
import numpy as np
from anndata import AnnData
import pandas as pd
from ._util import _is_na


def define_clonotypes(adata: AnnData) -> None:
    """Define clonotypes based on CDR3 region.

    The current definition of a clonotype is
    same CDR3 sequence for both primary and secondary
    TRA and TRB chains. 

    Parameters
    ----------
    adata
    flavor
        Currently, only "paried" is supported. 

    Returns
    -------
    Nothing, but adds a column `clonotype` to `adata.obs`. 
    
    """
    clonotype_col = np.array(
        [
            "clonotype_{}".format(x)
            for x in adata.obs.groupby(
                ["TRA_1_cdr3", "TRB_1_cdr3", "TRA_2_cdr3", "TRA_2_cdr3"]
            ).ngroup()
        ]
    )
    clonotype_col[adata.obs["has_tcr"] != "True"] = np.nan
    adata.obs["clonotype"] = clonotype_col


def tcr_dist(
    adata: AnnData,
    *,
    subst_mat=parasail.blosum62,
    gap_open: int = 8,
    gap_extend: int = 1
) -> None:
    """Compute the TCRdist on CDR3 sequences. 

    Currently takes into account only dominant alpha and dominant beta. 

    High-performance sequence alignment through parasail library [Daily2016]_

    Parameters
    ----------
    adata
    subst_mat
    gap_open
    gap_extend
    """
    # TODO parallelize
    for chain in ["TRA", "TRB"]:
        col = "{}_1_cdr3".format(chain)
        unique_cdr3s = adata.obs.loc[_is_na(adata.obs[col]), col].unique()

        dist_mat = np.empty([len(unique_cdr3s)] * 2)

        for i, s1 in enumerate(unique_cdr3s):
            profile = parasail.profile_create_16(s1, subst_mat)
            for j, s2 in enumerate(unique_cdr3s[i + 1 :]):
                r = parasail.sw_striped_profile_16(profile, s2, gap_open, gap_extend)
                dist_mat[i, j] = r.score

        dist_df = pd.DataFrame(dist_mat)
        dist_df.index = dist_df.columns = unique_cdr3s

        adata.uns["tcr_dist_alpha"] = dist_df


def alpha_diversity(adata: AnnData, key: str, *, flavor="shannon", inplace=True):
    """
    Alpha diversity within groups. 

    adata
        AnnData object to use
    key
        Column of `obs` by which the grouping will be performed. 
    """
    assert flavor == "shannon", "Other types not supported yet"

    # Could rely on skbio.math if more variants are required.
    def _shannon_entropy(freq):
        np.testing.assert_almost_equal(np.sum(freq), 1)
        return -np.sum(freq * np.log2(freq))

    tcr_obs = adata.obs.loc[adata.obs["has_tcr"] == "True", :]
    clono_counts = tcr_obs.groupby([key, "clonotype"]).size().reset_index(name="count")

    diversity = dict()
    for k in tcr_obs[key].unique():
        tmp_counts = clono_counts.loc[clono_counts[key] == k, "count"].values
        tmp_freqs = tmp_counts / np.sum(tmp_counts)
        diversity[k] = _shannon_entropy(tmp_freqs)

    return_dict = {"key": key, "diversity": diversity}
    if inplace:
        adata.uns["tcr_alpha_diversity"] = return_dict
    else:
        return return_dict