import numpy as np
import pandas as pd
import yaml
from pathlib import Path


# --------------------------------------------------
#  Safe calculation helpers
# --------------------------------------------------

def safe_div(numerator, denominator):
    """
    Safe division.
    Returns NaN when denominator is missing or zero.
    """

    if not isinstance(numerator, pd.Series):
        numerator = pd.Series(numerator)

    if not isinstance(denominator, pd.Series):
        denominator = pd.Series(
            denominator,
            index=numerator.index
        )

    numerator = numerator.astype("Float64")
    denominator = denominator.astype("Float64")

    result = numerator / denominator

    return result.where(
        denominator.notna() &
        (denominator != 0)
    )


def add_if_columns_exist(df, new_column, numerator, denominator):

    if (
        numerator in df.columns
        and denominator in df.columns
    ):
        df[new_column] = safe_div(
            df[numerator],
            df[denominator]
        )

    else:
        df[new_column] = pd.NA

    return df


def sum_available_columns(df, output_column, columns):

    available_columns = [
        col for col in columns
        if col in df.columns
    ]

    if available_columns:

        df[output_column] = (
            df[available_columns]
            .apply(pd.to_numeric, errors="coerce")
            .fillna(0)
            .sum(axis=1)
        )

    else:
        df[output_column] = pd.NA

    return df


# --------------------------------------------------
#  Dynamic calculation dependency handling
# --------------------------------------------------

def load_calculation_requirements():

    config_path = (
        Path(__file__).parent
        / "assets"
        / "column_mappings"
        / "calculated_variables.yaml"
    )

    with open(config_path, "r") as f:
        config = yaml.safe_load(f)

    required_columns = set()

    for calc in config["calculated_variables"]:

        required_columns.update(
            calc.get("numerator", [])
        )

        required_columns.update(
            calc.get("denominator", [])
        )

    return required_columns



def add_missing_calculation_inputs(df):

    required_columns = load_calculation_requirements()

    missing_columns = (
        required_columns
        -
        set(df.columns)
    )

    for column in missing_columns:
        df[column] = pd.NA

    return df



# --------------------------------------------------
# Calculation function
# --------------------------------------------------


def add_eavs_calculations(df):
    """
    Add calculated variables to the EAVS dataframe.
    """
    df = add_missing_calculation_inputs(df)
    ###########################################################
    # Registration
    ###########################################################

    df["pct_inactive"] = safe_div(
        df["inactive_voters"],
        df["registered_eligible_voters"],
    )

    df["pct_rejected_total_registration_forms"] = safe_div(
        df["rejected_registrations"],
        df["total_registrations_received"],
    )

    df["pct_rejected_new_valid_registration_forms"] = safe_div(
        df["rejected_registrations"],
        df["rejected_registrations"] + df["new_valid_registrations"],
    )

    ###########################################################
    # Mail/Fax Registration Sources
    ###########################################################

    df["pct_mail_fax_email_rejected"] = safe_div(
        df["rejected_registrations_mail_fax_email"],
        df["total_forms_mail_fax_email"],
    )

    df["pct_mail_fax_email_new_rejected"] = safe_div(
        df["rejected_registrations_mail_fax_email"],
        df["rejected_registrations_mail_fax_email"]
        + df["new_registrations_mail_fax_email"],
    )

    ###########################################################
    # In Person
    ###########################################################

    df["pct_inperson_rejected"] = safe_div(
        df["rejected_registrations_in_person"],
        df["total_forms_in_person"],
    )

    df["pct_inperson_new_rejected"] = safe_div(
        df["rejected_registrations_in_person"],
        df["rejected_registrations_in_person"]
        + df["new_registrations_in_person"],
    )

    ###########################################################
    # Online
    ###########################################################

    df["pct_online_rejected"] = safe_div(
        df["rejected_registrations_online"],
        df["total_forms_online"],
    )

    df["pct_online_new_rejected"] = safe_div(
        df["rejected_registrations_online"],
        df["rejected_registrations_online"]
        + df["new_registrations_online"],
    )

    ###########################################################
    # DMV
    ###########################################################

    df["pct_dmv_rejected"] = safe_div(
        df["rejected_registrations_dmv"],
        df["total_forms_dmv"],
    )

    df["pct_dmv_new_rejected"] = safe_div(
        df["rejected_registrations_dmv"],
        df["rejected_registrations_dmv"]
        + df["new_registrations_dmv"],
    )

    ###########################################################
    # Mandatory NVRA
    ###########################################################

    df["pct_mandatory_nvra_rejected"] = safe_div(
        df["rejected_registrations_mandatory_nvra"],
        df["total_forms_mandatory_nvra"],
    )

    df["pct_mandatory_nvra_new_rejected"] = safe_div(
        df["rejected_registrations_mandatory_nvra"],
        df["rejected_registrations_mandatory_nvra"]
        + df["new_registrations_mandatory_nvra"],
    )

    ###########################################################
    # Disability Agency
    ###########################################################

    df["pct_disability_agency_rejected"] = safe_div(
        df["rejected_registrations_disability_agency"],
        df["total_forms_disability_agency"],
    )

    df["pct_disability_agency_new_rejected"] = safe_div(
        df["rejected_registrations_disability_agency"],
        df["rejected_registrations_disability_agency"]
        + df["new_registrations_disability_agency"],
    )

    ###########################################################
    # Armed Forces
    ###########################################################

    df["pct_armed_forces_rejected"] = safe_div(
        df["rejected_registrations_armed_forces"],
        df["total_forms_armed_forces"],
    )

    df["pct_armed_forces_new_rejected"] = safe_div(
        df["rejected_registrations_armed_forces"],
        df["rejected_registrations_armed_forces"]
        + df["new_registrations_armed_forces"],
    )

    ###########################################################
    # Discretionary NVRA
    ###########################################################

    df["pct_discretionary_nvra_rejected"] = safe_div(
        df["rejected_registrations_discretionary_nvra"],
        df["total_forms_discretionary_nvra"],
    )

    df["pct_discretionary_nvra_new_rejected"] = safe_div(
        df["rejected_registrations_discretionary_nvra"],
        df["rejected_registrations_discretionary_nvra"]
        + df["new_registrations_discretionary_nvra"],
    )

    ###########################################################
    # Advocacy Groups
    ###########################################################

    df["pct_advocacy_groups_rejected"] = safe_div(
        df["rejected_registrations_advocacy_groups"],
        df["total_forms_advocacy_groups"],
    )

    df["pct_advocacy_groups_new_rejected"] = safe_div(
        df["rejected_registrations_advocacy_groups"],
        df["rejected_registrations_advocacy_groups"]
        + df["new_registrations_advocacy_groups"],
    )

    ###########################################################
    # Other Registration Sources
    ###########################################################

    sum_available_columns(
        df,
        "total_forms_other",
        [
            "total_forms_other_1",
            "total_forms_other_2",
            "total_forms_other_3"
        ]
        )


    sum_available_columns(
        df,
        "new_registrations_other",
        [
            "new_registrations_other_1",
            "new_registrations_other_2",
            "new_registrations_other_3"
        ]
    )


    sum_available_columns(
        df,
        "duplicate_registrations_other",
        [
            "duplicate_registrations_other_1",
            "duplicate_registrations_other_2",
            "duplicate_registrations_other_3"
        ]
    )


    sum_available_columns(
        df,
        "rejected_registrations_other",
        [
            "rejected_registrations_other_1",
            "rejected_registrations_other_2",
            "rejected_registrations_other_3"
        ]
    )

    df["pct_other_rejected"] = safe_div(
        df["rejected_registrations_other"],
        df["total_forms_other"],
    )

    df["pct_other_new_rejected"] = safe_div(
        df["rejected_registrations_other"],
        df["rejected_registrations_other"]
        + df["new_registrations_other"],
    )

    ###########################################################
    # Confirmation Notices
    ###########################################################

    df["pct_confirmation_status_unknown"] = safe_div(
        df["confirmation_notices_status_unknown"],
        df["confirmation_notices_sent_total"],
    )

    ###########################################################
    # Voter Removal
    ###########################################################

    base = (
        df["registered_eligible_voters"]
        + df["voters_removed_total_2020_2022"]
    )

    df["pct_registered_removed"] = safe_div(
        df["voters_removed_total_2020_2022"],
        base,
    )

    df["pct_registered_removed_felony"] = safe_div(
        df["voters_removed_felony"],
        base,
    )

    df["pct_removed_due_to_felony"] = safe_div(
        df["voters_removed_felony"],
        df["voters_removed_total_2020_2022"],
    )

    df["pct_registered_removed_nonresponse"] = safe_div(
        df["voters_removed_nonresponse"],
        base,
    )

    df["pct_removed_due_to_nonresponse"] = safe_div(
        df["voters_removed_nonresponse"],
        df["voters_removed_total_2020_2022"],
    )

    ###########################################################
    # Provisional Ballots (E1)
    ###########################################################

    df["pct_provisional_counted_full"] = safe_div(
        df["provisional_ballots_fully_counted"],
        df["provisional_ballots_cast_total"],
    )

    df["pct_provisional_counted_partial"] = safe_div(
        df["provisional_ballots_partially_counted"],
        df["provisional_ballots_cast_total"],
    )

    df["pct_provisional_rejected"] = safe_div(
        df["provisional_ballots_rejected_total"],
        df["provisional_ballots_cast_total"],
    )


    ###########################################################
    # Provisional Ballot Rejection Reasons (E3)
    ###########################################################

    df["pct_provisional_rejected_not_registered"] = safe_div(
        df["provisional_ballots_rejected_not_registered"],
        df["provisional_ballots_rejected_total"],
    )

    df["pct_provisional_rejected_wrong_jurisdiction"] = safe_div(
        df["provisional_ballots_rejected_wrong_jurisdiction"],
        df["provisional_ballots_rejected_total"],
    )

    df["pct_provisional_rejected_wrong_precinct"] = safe_div(
        df["provisional_ballots_rejected_wrong_precinct"],
        df["provisional_ballots_rejected_total"],
    )


    df["pct_provisional_rejected_no_id"] = safe_div(
        df["provisional_ballots_rejected_no_id"],
        df["provisional_ballots_rejected_total"],
    )


    df["pct_provisional_rejected_incomplete"] = safe_div(
        df["provisional_ballots_rejected_incomplete"],
        df["provisional_ballots_rejected_total"],
    )


    df["pct_provisional_rejected_ballot_missing"] = safe_div(
        df["provisional_ballots_rejected_ballot_missing"],
        df["provisional_ballots_rejected_total"],
    )


    df["pct_provisional_rejected_no_signature"] = safe_div(
        df["provisional_ballots_rejected_no_signature"],
        df["provisional_ballots_rejected_total"],
    )


    df["pct_provisional_rejected_non_matching_signature"] = safe_div(
        df["provisional_ballots_rejected_non_matching_signature"],
        df["provisional_ballots_rejected_total"],
    )


    df["pct_provisional_rejected_already_voted"] = safe_div(
        df["provisional_ballots_rejected_already_voted"],
        df["provisional_ballots_rejected_total"],
    )


    ###########################################################
    # Provisional Ballot Cast Reasons (E2)
    ###########################################################

    df["pct_provisional_not_on_eligible_list"] = safe_div(
        df["provisional_ballots_cast_voter_not_on_list"],
        df["provisional_ballots_cast_total"],
    )


    df["pct_provisional_lacked_id"] = safe_div(
        df["provisional_ballots_cast_voter_lacked_id"],
        df["provisional_ballots_cast_total"],
    )


    df["pct_provisional_official_challenge"] = safe_div(
        df["provisional_ballots_cast_challenged_by_official"],
        df["provisional_ballots_cast_total"],
    )


    df["pct_provisional_other_person_challenge"] = safe_div(
        df["provisional_ballots_cast_challenged_by_other"],
        df["provisional_ballots_cast_total"],
    )


    df["pct_provisional_not_resident"] = safe_div(
        df["provisional_ballots_cast_voter_not_resident"],
        df["provisional_ballots_cast_total"],
    )


    df["pct_provisional_registration_not_updated"] = safe_div(
        df["provisional_ballots_cast_registration_not_updated"],
        df["provisional_ballots_cast_total"],
    )


    df["pct_provisional_mail_ballot_not_surrendered"] = safe_div(
        df["provisional_ballots_cast_voter_did_not_surrender_mail"],
        df["provisional_ballots_cast_total"],
    )


    df["pct_provisional_judge_extended_hours"] = safe_div(
        df["provisional_ballots_cast_judge_extended_hours"],
        df["provisional_ballots_cast_total"],
    )


    ###########################################################
    # Provisional Other Reasons
    ###########################################################

    sum_available_columns(
        df,
        "provisional_ballots_cast_other_total",
        [
            "provisional_ballots_cast_other_1",
            "provisional_ballots_cast_other_2",
            "provisional_ballots_cast_other_3"
        ]
    )


    df["pct_provisional_other_reason"] = safe_div(
        df["provisional_ballots_cast_other_total"],
        df["provisional_ballots_cast_total"],
    )
    ###########################################################
    # Mail Ballots - Overall Totals (C1, C8, C9)
    ###########################################################

    # Total returned and rejected / transmitted
    df["pct_mail_ballots_rejected_transmitted"] = safe_div(
        df["mail_ballots_rejected_total"],
        df["mail_transmitted_total"],
    )


    # Total returned and rejected / returned
    df["pct_mail_ballots_rejected_returned"] = safe_div(
        df["mail_ballots_rejected_total"],
        df["mail_returned_by_voters"],
    )


    ###########################################################
    # Mail Ballot Rejection Reasons
    ###########################################################

    rejection_denominator = df["mail_ballots_rejected_total"]
    returned_denominator = df["mail_returned_by_voters"]


    # Late Ballot
    df["pct_rejected_late_of_rejections"] = safe_div(
        df["mail_ballots_rejected_late"],
        rejection_denominator,
    )

    df["pct_rejected_late_of_returned"] = safe_div(
        df["mail_ballots_rejected_late"],
        returned_denominator,
    )


    # Missing Voter Signature
    df["pct_rejected_missing_voter_signature_of_rejections"] = safe_div(
        df["mail_ballots_rejected_missing_voter_signature"],
        rejection_denominator,
    )

    df["pct_rejected_missing_voter_signature_of_returned"] = safe_div(
        df["mail_ballots_rejected_missing_voter_signature"],
        returned_denominator,
    )


    # Missing Witness Signature
    df["pct_rejected_missing_witness_signature_of_rejections"] = safe_div(
        df["mail_ballots_rejected_missing_witness_signature"],
        rejection_denominator,
    )

    df["pct_rejected_missing_witness_signature_of_returned"] = safe_div(
        df["mail_ballots_rejected_missing_witness_signature"],
        returned_denominator,
    )


    # Non Matching Signature
    df["pct_rejected_non_matching_signature_of_rejections"] = safe_div(
        df["mail_ballots_rejected_non_matching_voter_signature"],
        rejection_denominator,
    )

    df["pct_rejected_non_matching_signature_of_returned"] = safe_div(
        df["mail_ballots_rejected_non_matching_voter_signature"],
        returned_denominator,
    )


    # Unofficial Envelope
    df["pct_rejected_unofficial_envelope_of_rejections"] = safe_div(
        df["mail_ballots_rejected_unofficial_envelope"],
        rejection_denominator,
    )

    df["pct_rejected_unofficial_envelope_of_returned"] = safe_div(
        df["mail_ballots_rejected_unofficial_envelope"],
        returned_denominator,
    )


    # Ballot Missing From Envelope
    df["pct_rejected_ballot_missing_of_rejections"] = safe_div(
        df["mail_ballots_rejected_ballot_missing_from_envelope"],
        rejection_denominator,
    )

    df["pct_rejected_ballot_missing_of_returned"] = safe_div(
        df["mail_ballots_rejected_ballot_missing_from_envelope"],
        returned_denominator,
    )


    # Multiple Ballots
    df["pct_rejected_multiple_ballots_of_rejections"] = safe_div(
        df["mail_ballots_rejected_multiple_ballots_one_envelope"],
        rejection_denominator,
    )

    df["pct_rejected_multiple_ballots_of_returned"] = safe_div(
        df["mail_ballots_rejected_multiple_ballots_one_envelope"],
        returned_denominator,
    )


    # Envelope Not Sealed
    df["pct_rejected_envelope_not_sealed_of_rejections"] = safe_div(
        df["mail_ballots_rejected_envelope_not_sealed"],
        rejection_denominator,
    )

    df["pct_rejected_envelope_not_sealed_of_returned"] = safe_div(
        df["mail_ballots_rejected_envelope_not_sealed"],
        returned_denominator,
    )


    # Missing Address
    df["pct_rejected_missing_address_of_rejections"] = safe_div(
        df["mail_ballots_rejected_no_resident_address"],
        rejection_denominator,
    )

    df["pct_rejected_missing_address_of_returned"] = safe_div(
        df["mail_ballots_rejected_no_resident_address"],
        returned_denominator,
    )


    # Voter Deceased
    df["pct_rejected_deceased_of_rejections"] = safe_div(
        df["mail_ballots_rejected_voter_deceased"],
        rejection_denominator,
    )

    df["pct_rejected_deceased_of_returned"] = safe_div(
        df["mail_ballots_rejected_voter_deceased"],
        returned_denominator,
    )


    # Already Voted
    df["pct_rejected_already_voted_of_rejections"] = safe_div(
        df["mail_ballots_rejected_voter_already_voted"],
        rejection_denominator,
    )

    df["pct_rejected_already_voted_of_returned"] = safe_div(
        df["mail_ballots_rejected_voter_already_voted"],
        returned_denominator,
    )


    # First Time Voter ID
    df["pct_rejected_missing_documentation_of_rejections"] = safe_div(
        df["mail_ballots_rejected_missing_documentation"],
        rejection_denominator,
    )

    df["pct_rejected_missing_documentation_of_returned"] = safe_div(
        df["mail_ballots_rejected_missing_documentation"],
        returned_denominator,
    )


    # No Ballot Application
    df["pct_rejected_no_application_of_rejections"] = safe_div(
        df["mail_ballots_rejected_no_ballot_application"],
        rejection_denominator,
    )

    df["pct_rejected_no_application_of_returned"] = safe_div(
        df["mail_ballots_rejected_no_ballot_application"],
        returned_denominator,
    )


    ###########################################################
    # Other Mail Ballot Rejections (C9r+C9s+C9t)
    ###########################################################

    sum_available_columns(
        df,
        "mail_ballots_rejected_other_total",
        [
            "mail_ballots_rejected_other_1",
            "mail_ballots_rejected_other_2",
            "mail_ballots_rejected_other_3"
        ]
    )


    df["pct_rejected_other_of_rejections"] = safe_div(
        df["mail_ballots_rejected_other_total"],
        rejection_denominator,
    )


    df["pct_rejected_other_of_returned"] = safe_div(
        df["mail_ballots_rejected_other_total"],
        returned_denominator,
    )


    ###########################################################
    # Mail Ballot Processing
    ###########################################################

    df["mail_ballots_not_returned"] = (
        df["mail_transmitted_total"]
        - df["mail_returned_by_voters"]
    )




    return df