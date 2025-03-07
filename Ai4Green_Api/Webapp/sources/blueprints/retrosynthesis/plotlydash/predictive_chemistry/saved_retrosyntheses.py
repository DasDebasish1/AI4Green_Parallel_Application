import json
from datetime import datetime
from typing import Dict, List, Tuple

import dash_bootstrap_components as dbc
import pytz
from dash import callback_context, ctx, html
from flask_login import current_user
from sources import models, services
from sources.extensions import db
from sqlalchemy import func

from .utils import smiles_to_image


class SaveRetrosynthesis:
    """Validates and saves a retrosynthesis to the database. Updates the tracker number when finished"""

    def __init__(
        self,
        name: str,
        solved_routes: dict,
        conditions: dict,
        sustainability: dict,
        workbook_id: int,
        new_retrosynthesis_saved_tracker: int,
        retrosynthesis_uuid: str,
    ):
        self.name = name
        self.solved_routes = solved_routes
        self.conditions = conditions
        self.sustainability = sustainability
        self.workbook_id = workbook_id
        self.new_retrosynthesis_saved_tracker = new_retrosynthesis_saved_tracker
        self.retrosynthesis_uuid = retrosynthesis_uuid
        self.user_message = ""
        self.validation = ""

    def save_process(self) -> Tuple[str, int]:
        user_message, validation = self.validate_save()
        if validation == "success":
            self.save_retrosynthesis_to_db()
            self.new_retrosynthesis_saved_tracker += 1
        return user_message, self.new_retrosynthesis_saved_tracker

    def validate_save(self) -> Tuple[str, str]:
        """Validates the name and checks for it being a non-duplicate"""
        name_validation = self.validate_name()

        uuid_validation, duplicate_retrosynthesis_name = self.validate_non_duplicate()
        if name_validation == "failed" or uuid_validation == "failed":
            validation = "failed"
            if name_validation == "failed":
                user_message = (
                    "A retrosynthesis with this name already exists in this workbook. "
                    "Please use a different name."
                )
            if uuid_validation == "failed":
                user_message = f"This route has already been saved with the name {duplicate_retrosynthesis_name}"
        else:
            user_message = (f"Retrosynthesis: {self.name} saved successfully",)
            validation = "success"

        return user_message, validation

    def validate_name(self) -> str:
        """
        Checks the save name is unique within the workbook
        """
        unique_name_check = (
            db.session.query(models.Retrosynthesis)
            .filter(func.lower(models.Retrosynthesis.name) == self.name.lower())
            .join(models.WorkBook)
            .filter(models.WorkBook.id == self.workbook_id)
            .first()
        )
        if unique_name_check:
            return "failed"
        return "success"

    def validate_non_duplicate(self) -> Tuple[str, str]:
        """
        Checks the uuid is unique. Prevents user saving same retrosynthesis twice in the same workbook.
        """
        unique_check = (
            db.session.query(models.Retrosynthesis)
            .filter(models.Retrosynthesis.uuid == self.retrosynthesis_uuid)
            .join(models.WorkBook)
            .filter(models.WorkBook.id == self.workbook_id)
            .first()
        )
        if unique_check:
            return "failed", unique_check.name
        return "success", ""

    def save_retrosynthesis_to_db(self):
        target_smiles = self.solved_routes["routes"]["Route 1"]["steps"][0]["smiles"]
        solved_routes_json = json.dumps({"routes": self.solved_routes})
        conditions_json = json.dumps({"routes": self.conditions})
        sustainability_json = json.dumps({"routes": self.sustainability})
        services.retrosynthesis.add(
            self.name,
            target_smiles,
            self.retrosynthesis_uuid,
            self.workbook_id,
            conditions_json,
            sustainability_json,
            solved_routes_json,
        )


def make_retrosynthesis_card_list(selected_workbook_id: int) -> html.Div:
    retrosynthesis_list = services.retrosynthesis.list_from_workbook(
        selected_workbook_id
    )
    card_list = []
    for idx, retrosynthesis in enumerate(retrosynthesis_list):
        img_data = smiles_to_image(retrosynthesis.target_smiles)
        card_list.append(
            dbc.Card(
                className="mb-4 card-body",
                children=[
                    html.Div(
                        className="pl-3 pt-1 pb-1",
                        style={"margin-bottom": "-1rem"},
                        children=[
                            html.H4(retrosynthesis.name),
                            html.Div(
                                children=[
                                    html.P(retrosynthesis.creator_person.user.fullname),
                                    html.P(
                                        str(retrosynthesis.time_of_creation)[:-7],
                                        className="small text-muted",
                                    ),
                                ]
                            ),
                        ],
                    ),
                    html.Img(
                        src=img_data,
                        style={"background-color": "transparent", "opacity": "100"},
                    ),
                    html.Button(
                        "Reload",
                        className="btn-primary",
                        value=retrosynthesis.id,
                        n_clicks=0,
                        id={"type": "retrosynthesis-reload", "index": idx},
                    ),
                ],
            )
        )
    card_group = html.Div(children=card_list, className="card shadow-0 border")
    return card_group


def get_retrosynthesis_to_reload_id(reload_id_values: List[int]) -> int:
    """
    Takes the list of saved retrosynthesis ID the user has access to and uses the context to get the ID of the one
    they clicked using the index

    Args:
        reload_id_values - list of all saved retrosynthesis IDs in the selected workbook in the dropdown
    Returns:
        retrosynthesis_to_reload_id - the database ID of the retrosynthesis to reload.

    """
    retrosynthesis_to_reload = ctx.triggered_id
    retrosynthesis_to_reload_id = None
    if retrosynthesis_to_reload:
        index = retrosynthesis_to_reload["index"]
        retrosynthesis_to_reload_id = reload_id_values[index]
    return retrosynthesis_to_reload_id


def assert_button_clicked(reload_button_clicks) -> bool:
    # check button has been clicked to prevent firing on initial load
    zero_clicks = all(v == 0 for v in reload_button_clicks)
    changed_ids = [p["prop_id"] for p in callback_context.triggered][0]
    if "n_clicks" in changed_ids and not zero_clicks:
        return True
    return False


def get_reloaded_retrosynthesis(
    retrosynthesis_to_reload_id: int,
) -> Tuple[Dict, Dict, Dict, str]:
    retrosynthesis_to_reload = services.retrosynthesis.get(retrosynthesis_to_reload_id)
    routes = json.loads(retrosynthesis_to_reload.routes)["routes"]
    # route_dict_array = str_to_dict_array(routes)
    conditions = json.loads(retrosynthesis_to_reload.conditions)["routes"]
    # condition_dict_array = str_to_dict_array(conditions)
    sustainability = json.loads(retrosynthesis_to_reload.sustainability)["routes"]
    retrosynthesis_uuid = retrosynthesis_to_reload.uuid
    return routes, conditions, sustainability, retrosynthesis_uuid


def save_new_reaction_from_retrosynthesis(
    workbook_id: int, reaction_name: str, reaction_id: str, reaction_smiles: str
) -> str:
    """Makes a new reaction after user submits modal window"""
    # finds workgroup object (needs institution later)
    name_check = check_reaction(workbook_id, reaction_name)

    creator = current_user.Person

    # check for reaction id - catches errors caused if user has 2 tabs open
    reaction_id_check = services.reaction.get_from_reaction_id_and_workbook(
        reaction_id, workbook_id
    )
    if reaction_id_check:
        return "A reaction with this ID already exists. Please refresh the page and try again."

    # if the name check is passed then proceed with making the new reaction
    if "This reaction name is unique" in name_check:
        # make the reaction table dict with units set to default values
        reaction_table = json.dumps(
            {
                "amount_units": "mmol",
                "mass_units": "mg",
                "volume_units": "mL",
                "solvent_volume_units": "mL",
                "product_amount_units": "mmol",
                "product_mass_units": "mg",
                "reactant_masses": [],
                "reactant_masses_raw": [],
                "reactant_amounts": [],
                "reactant_amounts_raw": [],
                "reactant_volumes": [],
                "reactant_volumes_raw": [],
                "reactant_equivalents": [],
                "reactant_physical_forms": [],
                "reactant_densities": [],
                "reactant_concentrations": [],
                "reagent_names": [],
                "reagent_molecular_weights": [],
                "reagent_densities": [],
                "reagent_concentrations": [],
                "reagent_amounts": [],
                "reagent_amounts_raw": [],
                "reagent_equivalents": [],
                "reagent_physical_forms": [],
                "reagent_hazards": [],
                "reagent_masses": [],
                "reagent_masses_raw": [],
                "reagent_volumes": [],
                "reagent_volumes_raw": [],
                "solvent_volumes": [],
                "solvent_names": [],
                "solvent_concentrations": [],
                "solvent_hazards": [],
                "solvent_physical_forms": [],
                "product_amounts": [],
                "product_amounts_raw": [],
                "product_masses": [],
                "product_masses_raw": [],
                "product_physical_forms": [],
            }
        )

        summary_table = json.dumps(
            {
                "real_product_mass": "",
                "unreacted_reactant_mass": "",
                "reaction_temperature": "",
                "batch_flow": "-select-",
                "element_sustainability": "undefined",
                "isolation_method": "undefined",
                "catalyst_used": "-select-",
                "catalyst_recovered": "-select-",
                "custom_protocol1": "",
                "custom_protocol2": "",
                "other_hazards_text": "",
                "researcher": "",
                "supervisor": "",
                "radio_buttons": [],
            }
        )

        services.reaction.add(
            reaction_name,
            reaction_id,
            creator,
            workbook_id,
            reaction_smiles,
            reaction_table,
            summary_table,
        )
        # load sketcher
        return "New reaction made"
    else:
        return name_check


def check_reaction(workbook_id: int, reaction_name: str) -> str:
    """Checks the reaction name is unique"""
    # Tells the user they must give the reaction a name to save it
    if not reaction_name:
        return "The reaction must be given a name"
    if not reaction_name.replace(" ", "").replace("-", "").isalnum():
        return "Reaction names cannot contain special characters, only letters and numbers!"
    # Tells the user the reaction name must be unique
    reaction_name_check = services.reaction.get_from_name_and_workbook_id(
        reaction_name, workbook_id
    )
    if reaction_name_check is None:
        feedback = "This reaction name is unique"  # added to the reaction database'
    else:
        feedback = "This reaction name is already used. Please choose another name."
    return feedback
