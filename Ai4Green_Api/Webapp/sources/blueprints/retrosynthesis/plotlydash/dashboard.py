import re
import uuid
from typing import Dict, List, Tuple, Union

import dash
import dash_bootstrap_components as dbc
import dash_cytoscape as cyto
from dash import ALL, Input, Output, State, ctx, html
from flask import Flask,redirect
from rdkit import Chem
from sources import services
from flask_login import current_user
from . import classes, plotly_elements, style_sheets
from .predictive_chemistry import (
    conditions_api,
    cytoscape,
    dropdowns,
    process_user_route_file,
    retrosynthesis_api,
    saved_retrosyntheses,
    sustainability,
    tables,
    utils,
)
import json
cyto.load_extra_layouts()


def init_dashboard(server: Flask) -> classes.Dash:
    """Called on app initialization. Creates a Plotly Dash dashboard."""
    # make the dash app instance
    dash_app = classes.Dash(
        server=server,
        routes_pathname_prefix="/retrosynthesis/",
        external_stylesheets=[
            "/static/css/pagestyle.css",
        ],
    )
    # read api keys and urls from the yaml file
    retrosynthesis_api_key = server.config["RETROSYNTHESIS_API_KEY"]
    retrosynthesis_base_url = server.config["RETROSYNTHESIS_API_URL"]

    # Make the page layout. Elements imported plotly_elements.py
    dash_app.layout = html.Div(
        className="ml-1",
        children=[
            dbc.Row(
                className="g-0",
                children=[
                    # narrow column for sidebar and larger column for remainder of page
                    dbc.Col(
                        plotly_elements.tabs,
                        id="retrosynthesis-sidebar-root",
                        className="col-3 collapse show",
                    ),
                    dbc.Col(
                        className="col-9",
                        children=[
                            plotly_elements.header_and_inputs,
                            plotly_elements.retro_tree,
                        ],
                    ),
                ],
            ),
            plotly_elements.save_modal,
            plotly_elements.new_reaction_modal,
            plotly_elements.data_storage_elements,
        ],
        style=style_sheets.WebElementsStyles.CONTENT_STYLE,
    )

    """
    Callbacks
    """
    # @dash_app.callback( Input("open-tree", "n_click"))
    # def open_tree():
    #     return redirect("/retrosynthesis_tree")

    
    @dash_app.callback(Output("smiles-input", "value"), Input("url", "pathname"))
    def load_imported_smiles(url_dash: str) -> str:
        """
        Read smiles from the url and check if a valid molecule
        Args:
            # inputs
            url_dash - the url potentially containing the smiles imported from the sketcher
        Returns:
             smiles-input - smiles string or an empty string if not valid
        """
        imported_smiles = url_dash.split("/retrosynthesis/")[-1]
        # only update if it is a valid smiles
        imported_smiles = utils.encodings_to_smiles_symbols(imported_smiles)
        m = Chem.MolFromSmiles(imported_smiles, sanitize=False)
        if m is None:
            return dash.no_update
        if imported_smiles:
            return imported_smiles
        else:
            return ""

    @dash_app.callback(
        Output("save-modal-workbook-dropdown", "options"),
        Output("save-modal-workbook-dropdown", "value"),  # dropdown
        Output("save-modal-workbook-dropdown", "disabled"),
        Output("new-reaction-workbook-dropdown", "options"),
        Output("new-reaction-workbook-dropdown", "value"),  # dropdown
        Output("new-reaction-workbook-dropdown", "disabled"),
        Output("reload-workbook-dropdown", "options"),
        Output("reload-workbook-dropdown", "value"),  # dropdown
        Output("reload-workbook-dropdown", "disabled"),
        Output("save-functionality-status", "data"),
        Input("url", "pathname"),
    )
    def load_user_workbooks(
        url_dash: str,
    ) -> Tuple[List[dict], int, str, List[dict], int, str, List[dict], int, str]:
        """
        Loads all workbooks the user belongs to, populating the dropdowns
        and enabling/disabling the dropdowns and saving if there are no workbooks

        Args:
            # Inputs
            url_dash: Used as input to call function upon page load

        Returns:
            A list of:
                Repeated 3 times - once for each dropdown:
                    a list of dictionaries with workbook label and id
                    initially active workbook id
                    boolean to disable or enable the dropdown
                one string to enable or disable saving
        """
        (
            workbooks_dropdown,
            initial_dropdown_value,
        ) = dropdowns.make_workbooks_dropdown_options()
        if workbooks_dropdown:
            return 3 * (workbooks_dropdown, initial_dropdown_value, False) + (
                "enabled",
            )
        # if no workbooks dropdown
        return 3 * (workbooks_dropdown, None, True) + ("disabled",)

    @dash_app.callback(
        Output("open-save-modal", "disabled"),
        Output("open-new-reaction-modal", "disabled"),
        Input("save-functionality-status", "data"),
    )
    def save_features_handler(save_functionality_status: str) -> [bool, bool]:
        """
        Called on page load after function: 'load_user_workbooks'
        Disables or enables the save buttons

        Args:
            # Inputs
            save_functionality_status - disabled if user is not in a workbook

        Returns:
            2 bools to disable the save buttons if the user is not in a workbook or no update
        """
        if save_functionality_status == "disabled":
            return True, True
        return dash.no_update

    """Smiles input validation"""

    @dash_app.callback(
        Output("smiles-input", "pattern"),
        Input("smiles-input", "value"),
    )
    def smiles_check(smiles_input: str) -> str:
        """
        Called on changes to smiles input field
        Validates SMILES as valid before proceeding to retrosynthesis and highlights input field red if invalid SMILES.

        Args:
            # Inputs
            smiles_input: the target smiles string for retrosynthesis must translate to a valid molecule.

        Returns:
             pattern. Valid SMILES will remain unaltered. Invalid SMILES will have '_invalid' preceding and succeeding
        """
        smiles_input = "" if smiles_input is None else smiles_input
        smiles_input = smiles_input.strip()
        m = Chem.MolFromSmiles(smiles_input, sanitize=False)
        pattern = re.escape(smiles_input)
        if m is None or smiles_input == "":
            pattern = "_invalid_" + smiles_input + "_invalid"
        return pattern

    @dash_app.callback(
        Output("validated-smiles", "data"),
        State("smiles-input", "value"),
        Input("smiles-input", "pattern"),
    )
    def valid_smiles(smiles: str, smiles_regex: str) -> str:
        """
        Called after change to smiles-input pattern from function 'smiles_check'
        If SMILES is valid the SMILES is passed on to the validated smiles field to start retrosynthesis

        Args:
            # Input
            smiles_regex: the string checking if the smiles is valid, contains '_invalid' if invalid
            # State
            smiles: the target smiles

        Returns:
             smiles string to validated smiles data.Store if pattern is matched.
        """
        if smiles and smiles_regex and "_invalid" not in smiles_regex:
            return smiles
        return dash.no_update

    # def load_conditions(node):
    #     if node["reaction_smiles"]:
    #         conditions=conditions_api.get_reaction_condition(node["reaction_smiles"])
    #         processed_conditions = conditions_api.ProcessConditions(
    #         conditions, "",""
    #     ).process_conditions()
    #         conditions=[]
    #         for condition in processed_conditions:
    #             sustainabilit = sustainability.ReactionSustainabilityFlags(condition)
            
    #             sustainabilit.get_sustainability_flags()
    #         # # mean_score = np.mean(sustainability_flags)
    #         # # sustainability.average_sustainability_score = mean_score
    #             sustainability_dict = sustainabilit.to_dict()
    #             conditions.append(sustainability_dict)
    #         node["conditions"]=conditions
    #         node["sus"]=processed_conditions

    #     else:
    #         node["conditions"]=[]
    #         node["sus"]=[]
    #     children=[]
    #     for i,child in enumerate(node["children"]):
    #         children.append(load_conditions(child))
    #     node["children"]=children
    #     return node
    """ 

    Retrosynthesis process
    """

    @dash_app.callback(
        Output("loading-output-1", "loading_state"),
        Output("computed-retrosynthesis-routes", "data"),  # store
        Output("user-message", "children"),
        Output("computed-retrosynthesis-uuid", "data"),
        State("validated-smiles", "data"),
        State("smiles-input", "pattern"),
        State("iteration-input", "value"),
        Input("btn-retrosynthesis", "n_clicks"),
    )
    def start_new_retrosynthesis(
        validated_smiles: str, smiles_regex: str,iterations:int, n_clicks: int
    ) -> Tuple[bool, dict, str, str]:
        """
        Called when the user clicks the retrosynthesis button
        Starts the retrosynthesis process

        Args:
            # Inputs
            n_clicks - increments when the user clicks the retrosynthesis button
            # States
            validated_smiles - the validated smiles string
            smiles_regex - contains 'invalid' if smiles are not valid and prompts user to enter valid smiles

        Returns:
            bool -True to hide loading circle
            retrosynthesis routes as a dict
            a message to give the user feeedback
            The generated uuid for the retrosynthesis

        """
        changed_ids = [p["prop_id"] for p in dash.callback_context.triggered][0]
        if "btn-retrosynthesis" in changed_ids:
            if utils.smiles_not_valid(smiles_regex):
                return True, {}, "Please enter a valid SMILES", ""
            # if valid smiles then continue with the process
            if (iterations==None):
                iterations=100
            
            validated_smiles = utils.encodings_to_smiles_symbols(validated_smiles)
            validated_smiles=validated_smiles.replace("+","%2b")
            request_url = f"{retrosynthesis_base_url}/retrosynthesis_api/?key={retrosynthesis_api_key}&smiles={validated_smiles}&iterations={iterations}"
            (
                retro_api_status,
                api_message,
                solved_routes,Tree#add tree
            ) = retrosynthesis_api.retrosynthesis_api_call(
                request_url, retrosynthesis_base_url
            )
            with open(f'CacheTrees/{current_user.username}.json', 'w') as fp:
                json.dump(Tree, fp)
            unique_identifier = str(uuid.uuid4())
            if retro_api_status == "failed":
                return True, {}, api_message, ""
            retrosynthesis_output = {"uuid": unique_identifier, "routes": solved_routes}
            #add
            
         
            # Tree=load_conditions(Tree)
            
            ###
            return (
                True,
                retrosynthesis_output,
                f"Interactive display for retrosynthesis of {validated_smiles}",
                unique_identifier,
            )
        return dash.no_update

    @dash_app.callback(
        Output("conditions-loader", "loading_state"),
        Output("computed-conditions-data", "data"),
        State("computed-retrosynthesis-uuid", "data"),
        Input("computed-retrosynthesis-routes", "data"),
    )
    def new_conditions(
        unique_identifier: str, solved_routes: dict
    ) -> Tuple[bool, dict]:
        """
        Called upon completion of a new retrosynthesis routes
        Generates conditions for each corresponding forward reaction in the retrosynthetic routes

        Args:
            # Inputs
            solved_routes - the solved retrosynthetic routes
            # States
            unique_identifier - the uuid for the retrosynthesis

        Returns:
            a bool, True to quit the loading circle.
            A dbc table containing the conditions data

        Fires on completion of new retrosynthesis routes
        Inputs: Retrosynthesis routes - using smiles of reactants and products
        makes an api call to get the condition data from the reaction smiles.
        Condition data includes: accuracy score, temperature, solvent, reagents, catalysts
        Returns a Bool to quit the loading circle and a dbc table with conditions data
        """
        if solved_routes and solved_routes != {}:
            conditions = conditions_api.get_conditions(solved_routes["routes"])

            # all_conditions = get_all_conditions(
            #     solved_routes["routes"], conditions_base_url, conditions_api_key
            # )
            conditions_output = {"uuid": unique_identifier, "routes": conditions}
            return True, conditions_output
        return dash.no_update

    @dash_app.callback(
        Output("active-conditions-data", "data"),
        Input("computed-conditions-data", "data"),
        Input("reloaded-conditions-data", "data"),
        Input("user-uploaded-conditions-data", "data"),
    )
    def determine_active_conditions(
        computed_conditions: dict,
        reloaded_conditions: dict,
        user_uploaded_conditions: dict,
    ) -> dict:
        """
        Called when one of: new conditions data computed, reloading a retrosynthesis, user uploaded a retrosynthesis
        The context is used to select which one of these conditions sources has changed and is therefore active

        Args:
            # Inputs
            computed_conditions - from the conditions API
            reloaded_conditions - from the database
            user_uploaded_conditions - from a file upload

        Returns:
            the active condition set as a dictionary
        """
        condition_set = ctx.triggered[0]["value"]
        if condition_set:
            return condition_set
        return dash.no_update

    @dash.callback(
        Output("computed-sustainability-data", "data"),
        Input("computed-conditions-data", "data"),
    )
    def sustainability_assessment(all_conditions: dict) -> dict:
        """
        Called when condition predictions have been processed and outputted to html element.
        Gets the sustainability data for a route from the conditions_dict which contains all the necessary data

        Args:
            all_conditions - conditions data in dictionary

        Returns:
            sustainability_for_all_routes - dictionary of sustainability data
        """
        if all_conditions:
            sustainability_for_all_routes = (
                sustainability.get_sustainability_for_all_routes(
                    all_conditions["routes"]
                )
            )
        
            return sustainability_for_all_routes
        return dash.no_update

    @dash.callback(
        Output("active-sustainability-data", "data"),
        Input("computed-sustainability-data", "data"),
        Input("reloaded-sustainability-data", "data"),
        Input("user-uploaded-route-sustainability-data", "data"),
    )
    def determine_active_sustainability_data(
        sustainability_data: dict,
        reloaded_sustainability: dict,
        user_uploaded_sustainability: dict,
    ) -> dict:
        """

        Fires on a new retrosynthesis when the conditions api has returned data or when reloading a retrosynthesis.
        Data is used from whichever input triggered the callback
        Returns a list of sustainability data
        """
        active_sustainability_data = ctx.triggered[0]["value"]
        if active_sustainability_data:
            return active_sustainability_data
        return dash.no_update

    @dash_app.callback(
        Output("weighted-sustainability-data", "data"),
        State("active-retrosynthesis-uuid", "data"),
        Input("active-sustainability-data", "data"),
        Input(
            component_id={"type": "sustainability-weighting-slider", "property": ALL},
            component_property="value",
        ), 
    )
    def apply_weightings(
        unique_identifier: str,
        sustainability_data: dict,
        sustainability_weightings: List[int],
    ) -> dict:
        """
        Called when user changes the metric weighting slides or when the active sustainability data changes
        Applies weightings to the sustainability data to generate the weighted sustainability data for each step
        and the route as a whole.

        Args:
            # Inputs
            sustainability - dict of sustainability data
            sustainability_weightings - list of the metric weightings taken from the slider
            # States
            unique_identifier - the uuid for the retrosynthesis

        Returns:
            An updated weighted sustainability dictionary.
        """
        if sustainability_weightings and sustainability_data:
            # apply weightings to each route to obtain a weighted median for each route as a whole.
            for route_label, route in sustainability_data.items():
                route_median = sustainability.weighted_median_for_route(
                    route, sustainability_weightings
                )
                route["route_average"]["weighted_median"] = route_median
            # 2) apply weighting to each step of the route
            for route in sustainability_data.values():
                sustainability.weighted_median_for_each_step(
                    route, sustainability_weightings
                )
            weighted_sustainability_output = {
                "uuid": unique_identifier,
                "routes": sustainability_data,
            }
            return weighted_sustainability_output
        return dash.no_update

    @dash.callback(
        Output("active-retrosynthesis-uuid", "data"),
        Input("computed-retrosynthesis-uuid", "data"),
        Input("reloaded-retrosynthesis-uuid", "data"),
        Input("user-uploaded-route-uuid", "data"),
    )
    def determine_active_uuid(
        computed_uuid: str, reloaded_uuid: str, user_uploaded_uuid: str
    ) -> str:
        """
        Called when one of: a new retrosynthesis is made, a retrosynthesis is reloaded, retrosynthesis file upload
        Determines the active uuid by using the context

        Args:
            # Inputs
            computed_uuid - for a newly computed retrosynthesis from the smiles input field
            reloaded_uuid - from the database
            user_uploaded_uuid - newly computed after user has uploaded a routes/conditions file

        Returns:
            The active uuid string
        """
        active_uuid_data = ctx.triggered[0]["value"]
        if active_uuid_data:
            return active_uuid_data
        return dash.no_update

    @dash_app.callback(
        Output("active-retrosynthesis-routes", "data"),
        Input("computed-retrosynthesis-routes", "data"),
        Input("reloaded-retrosynthesis-routes", "data"),
        Input("user-uploaded-route", "data"),
    )
    def determine_active_retrosynthesis_routes(
        computed_retrosynthesis_routes: dict,
        reloaded_retrosynthesis_routes: dict,
        user_route: dict,
    ) -> dict:
        """
        Called when one of: a new retrosynthesis is made, a retrosynthesis is reloaded, retrosynthesis file upload
        Determines the active routes using the context

        Args:
            # Inputs
             computed_retrosynthesis_routes - fresh from the retrosynthesis api
             reloaded_retrosynthesis_routes - from the database
             user_route - from the user uploaded file

        Returns:
            The active retrosynthestic routes
        """
        active_retrosynthesis_data = ctx.triggered[0]["value"]
        if active_retrosynthesis_data:
            return active_retrosynthesis_data
        return dash.no_update

    @dash_app.callback(
        Output("routes-dropdown", "value"),
        Output("routes-dropdown", "options"),
        Input("active-retrosynthesis-routes", "data"),
        Input("active-conditions-data", "data"),
        Input("weighted-sustainability-data", "data"),
    )
    def populate_routes_dropdown(
        active_retrosynthesis: dict,
        active_conditions: dict,
        active_weighted_sustainability: dict,
    ) -> Tuple[str, List[dict]]:
        """
        Populates the routes dropdown at the top of the page. Checks all unique identifiers in dictionaries match
        this confirms they are from the same retrosynthesis

        Args:
            # Inputs
            active_retrosynthesis - dictionary with retrosynthesis data of retrosynthesis to display
            active_conditions - dictionary with conditions data of retrosynthesis to display
            active_weighted_sustainability - dictionary with sustainability data of retrosynthesis to display

        Returns:
            Initial route dropdown value defaults to "Route 1"
            List of route options coloured by their sustainability
        """

        if (
            active_retrosynthesis
            and active_conditions
            and active_weighted_sustainability
        ):
            unique_identifier_list = [
                x["uuid"]
                for x in [
                    active_retrosynthesis,
                    active_conditions,
                    active_weighted_sustainability,
                ]
            ]
            # all unique identifiers should match - indicating they come from the same retrosynthesis
            if all(
                unique_identifier == unique_identifier_list[0]
                for unique_identifier in unique_identifier_list
            ):
                route_options = dropdowns.routes(
                    active_retrosynthesis, active_weighted_sustainability
                )
                return (
                    "Route 1",
                    route_options,
                )
        return dash.no_update

    @dash_app.callback(
        Output("routes-dropdown", "style"),
        State("routes-dropdown", "options"),
        Input("routes-dropdown", "value"),
    )
    def update_route_dropdown_background_colour(
        options: List[dict], active_route: str
    ) -> dict:
        """
        Called when the routes dropdown changes
        Updates the background colour to the weighted median sustainability of the active route in the dropdown

        Args:
            # Inputs
            active_route - the name of the active route in the pattern Route 1, Route 2, etc.
            # States
            options - the options in the dropdown including background colour data

        Returns:
            a dict with the background colour reflective of the sustainability of the selected route
        """

        if options and active_route:
            # get background colour
            for option in options:
                if option["value"] == active_route:
                    background_colour = option["label"]["props"]["style"][
                        "background-color"
                    ]
                    return {"background-color": background_colour, "width": "100%"}
        return dash.no_update

    @dash_app.callback(
        Output("retrosynthesis-cytoscape", "elements"),
        Output("retrosynthesis-cytoscape", "stylesheet"),
        State("active-retrosynthesis-routes", "data"),
        Input("routes-dropdown", "value"),
    )
    def display_retrosynthesis(
        active_retrosynthesis: dict, selected_route: str
    ) -> Tuple[List[dict], List[dict]]:
        """
        Called when there is a change to the routes dropdown or active routes
        Create the nodes, edges, and stylesheet to generate the interactive cytoscape

        Args:
            # Inputs
            selected_route - e.g., Route 1
            # States
            active_retrosynthesis - the active retrosynthetic routes

        Returns:
            style_sheet - a list of styles as dictionaries. Each has a selector and a style
            elements - a list of nodes and edges as dictionaries. node_id is used to identify nodes and connect nodes

        """
        if active_retrosynthesis and selected_route:
            retro_cytoscape = cytoscape.RetrosynthesisCytoscape(
                active_retrosynthesis["routes"], selected_route
            )
            elements = retro_cytoscape.make_cytoscape_elements()
            style_sheet = retro_cytoscape.make_cytoscape_stylesheet()
            return (
                elements,
                style_sheet,
            )
        else:
            return dash.no_update

    @dash_app.callback(
        Output("route-feedback", "children"),
        State("active-retrosynthesis-routes", "data"),
        Input("weighted-sustainability-data", "data"),
        Input("routes-dropdown", "value"),  # dropdown
    )
    def generate_route_table(
        retrosynthesis_data: dict, weighted_sustainability: dict, selected_route: str
    ) -> Tuple[dbc.Table, dbc.Table]:
        """
        Called when there is a change to routes dropdown or the active sustainability data
        Generates the two tables in the routes tab. The brief description table
        and the colour-coded step sustainability analysis table.

        Args:
            # Inputs
            weighted_sustainability - the routes sustainability with metric weightings applied
            selected_route - the title of the active route, e.g., 'Route 1'
            # States
            retrosynthesis_data - the active retrosynthetic routes

        Returns:
            Two tables shown on the 'Routes' tab. One with general data and the other sustainability data.
        """
        if retrosynthesis_data and selected_route and weighted_sustainability:
            route_tables = tables.routes(
                retrosynthesis_data["routes"],
                selected_route,
                weighted_sustainability["routes"],
            )
            return route_tables
        return dash.no_update

    """
    Saving Retrosynthesis Results
    """

    @dash_app.callback(
        Output("save-modal", "is_open"),
        Input("open-save-modal", "n_clicks"),
        Input("close-save-modal", "n_clicks"),
        State("save-modal", "is_open"),
    )
    def toggle_modal(n1: int, n2: int, is_open: bool) -> bool:
        """
        Called when user opens or closes 'Save to Workbook' button
        Toggles the modal window open and shut.
        Args:
            # Inputs
            n1 - Calls function if the open button is clicked
            n2 - Calls function if the closed button is clicked
            # States
            is_open - current open status. False means closed before the user click and vice versa for True.

        Returns:
            bool - opposite of current bool.
        """
        if n1 or n2:
            return not is_open
        return is_open

    @dash_app.callback(
        Output("new-reaction-modal", "is_open"),
        Input("open-new-reaction-modal", "n_clicks"),
        Input("close-new-reaction-modal", "n_clicks"),
        State("new-reaction-modal", "is_open"),
    )
    def toggle_new_reaction_modal(n1: int, n2: int, is_open: bool) -> bool:
        """
        Called when user opens or closes 'Export to Sketcher' button on the Reactions tab.
        Toggles the modal window open and shut
        Args:
            # Inputs
            n1 - Calls function if the open button is clicked
            n2 - Calls function if the closed button is clicked
            # States
            is_open - current open status. False means closed before the user click and vice versa for True.

        Returns:
            bool - opposite of current bool.
        """
        if n1 or n2:
            return not is_open
        return is_open

    @dash_app.callback(
        Output("modal-save-message", "children"),
        Output("new-retrosynthesis-saved-flag", "data"),
        State("save-modal-name", "value"),
        State("active-retrosynthesis-routes", "data"),
        State("active-conditions-data", "data"),
        State("active-sustainability-data", "data"),
        State("save-modal-workbook-dropdown", "value"),
        State("new-retrosynthesis-saved-flag", "data"),
        State("save-functionality-status", "data"),
        State("active-retrosynthesis-uuid", "data"),
        Input("save-modal-save-button", "n_clicks"),
    )
    def save_retrosynthesis(
        name: str,
        solved_routes: dict,
        conditions: dict,
        sustainability_data: dict,
        workbook_id: int,
        new_retrosynthesis_saved_tracker: int,
        functionality_status: str,
        retrosynthesis_uuid: str,
        click_save: int,
    ) -> [str, int]:
        """
        Called when the user clicks 'Save' to save a retrosynthesis
        Validates and saves the current retrosynthesis to the database.
        Args:
            # Inputs:
            click_save - clicking the save button increments the interger, calling this function
            # States:
            name: name of saved retrosynthesis
            solved_routes: retrosynthetic route data dict
            conditions: condition data dict
            sustainability_data: sustainability data dict
            workbook_id: workbook database primary key id
            new_retrosynthesis_saved_tracker: tracker to update saved retrosynthesis list upon change
            functionality_status: values of either 'enabled' or 'disabled' to determine if saving is active

        Returns:
            User message
            tracker int to indicate if changes to the saved reaction list are needed upon successful save.
        """
        if utils.functionality_disabled_check(functionality_status):
            return dash.no_update
        changed_ids = [p["prop_id"] for p in dash.callback_context.triggered][0]
        if "save-modal-save-button" in changed_ids and solved_routes:
            (
                user_message,
                retrosynthesis_saved_tracker,
            ) = saved_retrosyntheses.SaveRetrosynthesis(
                name,
                solved_routes,
                conditions,
                sustainability_data,
                workbook_id,
                new_retrosynthesis_saved_tracker,
                retrosynthesis_uuid,
            ).save_process()
            print(f"{retrosynthesis_saved_tracker=}{user_message=}")
            return user_message, retrosynthesis_saved_tracker
        return dash.no_update

    @dash_app.callback(
        Output("saved-results-list", "children"),
        Input("reload-workbook-dropdown", "value"),
        Input("new-retrosynthesis-saved-flag", "data"),
        State("save-functionality-status", "data"),
    )
    def show_retrosynthesis_list(
        selected_workbook_id: int,
        new_retrosynthesis_saved: int,
        functionality_status: str,
    ):
        """
        Called when there is a change to the workbook dropdown or a new retrosynthesis is saved

        Uses the workbook ID to display an HTML card for each retrosynthesis belonging to that workbook
        in the save list for reload.

        Args:
            # Inputs
            new_retrosynthesis_saved - incremented when a new retrosynthesis is saved and causes function to be called
            # States
            selected_workbook_id - Database ID of the selected workbook in the dropdown
            functionality_status - 'enabled' or 'disabled' to allow/disallow saving related methods

        Returns:
            card_group - A list of retrosynthesis as Dash Bootstrap component HTML Cards.
        """
        if utils.functionality_disabled_check(functionality_status):
            return dash.no_update
        changed_ids = [p["prop_id"] for p in dash.callback_context.triggered][0]
        if (
            "new-retrosynthesis-saved-flag" in changed_ids
            or "reload-workbook-dropdown" in changed_ids
        ):
            card_group = saved_retrosyntheses.make_retrosynthesis_card_list(
                selected_workbook_id
            )
            return card_group
        return dash.no_update

    @dash_app.callback(
        Output("reloaded-retrosynthesis-routes", "data"),
        Output("reloaded-conditions-data", "data"),
        Output("reloaded-sustainability-data", "data"),
        Output("reloaded-retrosynthesis-uuid", "data"),
        State(
            component_id={"type": "retrosynthesis-reload", "index": ALL},
            component_property="value",
        ),
        Input(
            component_id={"type": "retrosynthesis-reload", "index": ALL},
            component_property="n_clicks",
        ),
        State("save-functionality-status", "data"),
    )
    def reload_retrosynthesis(
        reload_id_values: List[int],
        reload_button_clicks: List[int],
        functionality_status: str,
    ) -> Tuple[dict, dict, dict, str]:
        """
        Called when a 'reload' button is clicked

        Args:
            # Inputs
            reload_button_clicks - The reloaded button which is clicked has a 1 in that index otherwise 0 for unclicked.
            # States
            reload_id_values - The retrosynthesis IDs which could be reloaded
            functionality_status - 'enabled' or 'disabled'

        Returns:
            A dictionary for each the retrosynthesis, conditions, sustainability, and the retrosynthesis uuid
        """
        if utils.functionality_disabled_check(functionality_status):
            return dash.no_update
        # find the element that was clicked - if one was clicked
        if reload_id_values and reload_button_clicks:
            if saved_retrosyntheses.assert_button_clicked(reload_button_clicks):
                retrosynthesis_to_reload_id = (
                    saved_retrosyntheses.get_retrosynthesis_to_reload_id(
                        reload_id_values
                    )
                )
                (
                    retrosynthesis_data,
                    condition_data,
                    sustainability_data,
                    retrosynthesis_uuid,
                ) = saved_retrosyntheses.get_reloaded_retrosynthesis(
                    retrosynthesis_to_reload_id
                )
                return (
                    retrosynthesis_data,
                    condition_data,
                    sustainability_data,
                    retrosynthesis_uuid,
                )
        return dash.no_update

    """
    Compound sidebar
    """

    @dash_app.callback(
        Output("compound-feedback", "children"),
        Output("tapped-compound-image", "src"),
        Input("retrosynthesis-cytoscape", "tapNodeData"),
    )
    def display_compound_node_data(
        tapped_node: dict,
    ) -> Tuple[Union[dbc.Table, str], str]:
        """
        Called when user taps a compound node in the cytoscape interface.
        Uses the compound smiles to make an image and find the compound in the database if it is present

        Args:
            # Inputs
            tapped_node - corresponds to a molecule with the SMILES inside the dictionary

        Returns:
            either the compound data table or a string stating compound is not in the database
            a svg image of the compound
        """
        if tapped_node == ["smiles"] or tapped_node is None:
            return dash.no_update
        smiles = tapped_node["smiles"]
        img_data = utils.smiles_to_image(smiles)
        if not img_data:
            img_data = utils.alt_smiles_to_image(smiles)
        compound_feedback = tables.compound(smiles)
        return compound_feedback, img_data

    """
    Conditions
    """

    @dash_app.callback(
        Output("reaction-conditions-list", "data"),
        Output("reaction-sustainability-list", "data"),
        Output("conditions-dropdown", "value"),  # dropdown
        Output("conditions-dropdown", "options"),
        State("routes-dropdown", "value"),
        State("active-conditions-data", "data"),
        State("active-sustainability-data", "data"),
        Input("retrosynthesis-cytoscape", "tapNodeData"),
        Input("weighted-sustainability-data", "data"),
    )
    def fill_conditions_dropdown(
        route: str,
        conditions_data: Dict,
        sustainability_data: Dict,
        tapped_node: Dict,
        weighted_sustainability_data: Dict,
    ) -> Tuple[List[Dict], List[Dict], str, List[Dict]]:
        """
        Called when a user clicks on a compound node
        Finds the data for all the condition sets (up to 10) for a forward reaction and makes the dropdown for this.

        Args:
            # Inputs
            tapped_node - The node the user has clicked on. product SMILES used to look up current reaction
            # States
            route - The current route label - needed to look up current route
            conditions_data - The reaction conditions are extracted from this dictionary
            sustainability_data - The reaction sustainability data are extracted from this dictionary

        Returns:
            rxn_conditions - conditions for the current reaction
            rxn_sustainability - sustainability for the current reaction
            'Condition Set 1' as the default active condition set
            dropdown_options - to populate the condition set dropdown.

        """
        if route and conditions_data and sustainability_data:
            if not tapped_node["reaction_smiles"]:
                return [{}], [{}], "Terminal node.", [{}]
            (
                rxn_conditions,
                rxn_sustainability,
                dropdown_options,
            ) = dropdowns.make_conditions_dropdown(
                route,
                conditions_data["routes"],
                weighted_sustainability_data,
                tapped_node,
            )
            return (
                rxn_conditions,
                rxn_sustainability,
                "Condition Set 1",
                dropdown_options,
            )
        return dash.no_update

    @dash_app.callback(
        Output("conditions-dropdown", "style"),
        State("conditions-dropdown", "options"),
        Input("conditions-dropdown", "value"),
    )
    def update_conditions_dropdown_background_colour(
        options: List[dict], active_condition_set: str
    ) -> dict:
        """
        Called when the conditions dropdown changes
        Updates the background colour to the weighted median sustainability of the active condition set in the dropdown

        Args:
            # Inputs
            active_condition set - the name of the active condition set in the pattern Condition Set 1, Condition Set 2, etc.
            # States
            options - the options in the dropdown including background colour data

        Returns:
            a dict with the background colour reflective of the sustainability of the selected condition set
        """

        if options and active_condition_set:
            # get background colour
            for option in options:
                if option["value"] == active_condition_set:
                    background_colour = option["label"]["props"]["style"][
                        "background-color"
                    ]
                    return {"background-color": background_colour, "width": "100%"}
        return dash.no_update

    @dash_app.callback(
        Output("reaction-conditions", "children"),
        # Output('reaction-sustainability', 'children'),
        State("reaction-conditions-list", "data"),
        State("reaction-sustainability-list", "data"),
        Input("conditions-dropdown", "value"),
    )
    def generate_reaction_table(
        conditions_options: List[dict],
        sustainability_options: List[dict],
        conditions_dropdown_value: str,
    ) -> Union[dbc.Table, str]:
        """
        Called when the conditions dropdown changes or clicks a chemical node to show details of the predicted reaction
        Generates the reaction table in the reactions tab with the details predicted to perform the forward reaction
        colour coded by their sustainability.

        Args:
            # Inputs
            conditions_dropdown_value - The label/value of the active condition set in format: 'Condition Set 1'
            # States
            conditions_options - Dict with the conditions for the forward reaction to be shown in the table
            sustainability_options - Dict with the sustainability for the conditions - colours the rows in the table.

        Returns:
            Either the colour-coded conditions table for the forward reaction or a string explaining terminal node
            has no reaction.
        """
        if conditions_dropdown_value != "Terminal node.":
            conditions_table = tables.reaction( 
                conditions_options, sustainability_options, conditions_dropdown_value
            )
            return conditions_table
        elif conditions_dropdown_value:
            return "Terminal node has no reaction"
        return dash.no_update

    """Route data"""

    @dash_app.callback(
        Output("reaction-smiles", "data"),
        Output("tapped-reaction-image", "src"),
        Output("reaction-class", "children"),
        Input("retrosynthesis-cytoscape", "tapNodeData"),
    )
    def display_reaction(tapped_node: dict) -> Tuple[str, str, str]:
        """
        Called when user clicks on a compound node
        Uses the reaction string to make a png image with the reaction class above the image in the Reactions tab.

        Args:
            # Inputs
            tapped_node - dictionary contains reaction_smiles and reaction_class of the active reaction

        Returns:
            reaction_smiles of the active reaction
            img_data for the current reaction as a png string
            reaction_class of the active reaction.
        """
        if not tapped_node:
            return dash.no_update
        reaction_class = tapped_node["label"]
        reaction_smiles = tapped_node["reaction_smiles"]
        if reaction_smiles:
            img_data = utils.reaction_smiles_to_image(reaction_smiles)
        else:
            img_data = utils.alt_smiles_to_image(
                tapped_node["smiles"]
            )  # rdkit method best for single singles
        return reaction_smiles, img_data, reaction_class

    @dash_app.callback(
        Output("new-reaction-id", "value"),
        State("save-functionality-status", "data"),
        Input("new-reaction-workbook-dropdown", "value"),
    )
    def update_new_reaction_id(functionality_status: str, workbook_id: int) -> str:
        """
        Called when changing the workbook dropdown and finds the next reaction ID. This is needed to make a new reaction

        Args:
            # Inputs
            workbook_id - the ID of the selected workbook in the dropdown
            # States
            functionality_status - saving methods are 'enabled' or 'disabled'

        Returns:
            the next auto-incremented reaction_id value as a string. e.g., WB1-001

        """
        if utils.functionality_disabled_check(functionality_status):
            return dash.no_update
        return services.reaction.next_reaction_id_for_workbook(workbook_id)

    @dash_app.callback(
        Output("new-reaction-url", "data"),
        Output("modal-new-reaction-message", "children"),
        State("url", "pathname"),
        State("new-reaction-workbook-dropdown", "value"),
        State("new-reaction-name", "value"),
        State("new-reaction-id", "value"),
        State("reaction-smiles", "data"),
        State("save-functionality-status", "data"),
        Input("new-reaction-data-submit", "n_clicks"),
    )
    def new_reaction(
        current_url: str,
        workbook_id: int,
        reaction_name: str,
        reaction_id: str,
        reaction_smiles: str,
        functionality_status: str,
        n_clicks: int,
    ) -> Tuple[str, str]:
        """
        Called when user clicks new reaction button - to export reaction from retrosynthesis to new ELN entry
        Performs validation and then if successful saves Reaction to database and opens in new tab

        Args:
            # Inputs
            n_clicks - integer changes when user clicks the new reaction button
            # States
            current_url - to get the base url
            workbook_id - ID used to save the new reaction
            reaction_name - save to database under this name
            reaction_id - saved to database under this id
            reaction_smiles - saved to database
            functionality_status - 'enabled' or 'disabled'

        Returns:
            URL of the new reaction and opens in a new tab
            A feedback message to user in case of failure

        """
        if utils.functionality_disabled_check(functionality_status):
            return dash.no_update
        changed_ids = [p["prop_id"] for p in dash.callback_context.triggered][0]
        if "new-reaction-data-submit" in changed_ids:
            if not reaction_smiles:
                return "", "Click on the desired product to export as new reaction"
            # check if - name is unique
            workbook_object = utils.get_workbook_from_id(workbook_id)
            result = saved_retrosyntheses.save_new_reaction_from_retrosynthesis(
                workbook_id, reaction_name, reaction_id, reaction_smiles
            )
            if result == "New reaction made":
                workgroup_name = workbook_object.group.name
                workbook_name = workbook_object.name
                base_url = current_url.split("retrosynthesis")[0]
                new_url = f"{base_url}sketcher/{workgroup_name}/{workbook_name}/{reaction_id}/no"
                return new_url, "New reaction made!"
            return "", result
        return dash.no_update

    @dash_app.callback(
        Output("url", "pathname"),
        State("save-functionality-status", "data"),
        Input("new-reaction-url", "data"),
    )
    def go_to_new_reaction(functionality_status: str, new_url: str) -> str:
        """
        Called when a new reaction is successfully made
        Opens a new reaction in a new tab. Checks url is present first.

        Args:
            functionality_status: 'enabled' or 'disabled'
            new_url: the url which is opened in a new tab for the new ELN reaction entry.
        """
        if utils.functionality_disabled_check(functionality_status):
            return dash.no_update
        if new_url:
            return new_url
        return dash.no_update

    """
    Callbacks for user inputted routes
    """

    @dash_app.callback(
        Output("user-uploaded-route", "data"),
        Output("user-uploaded-conditions-data", "data"),
        Output("user-uploaded-route-sustainability-data", "data"),
        Output("user-uploaded-route-uuid", "data"),
        Input("upload-route-button", "contents"),
        State("upload-route-button", "filename"),
    )
    def update_output(contents: str, filename: str) -> Tuple[dict, dict, dict, str]:
        """
        Called when a user clicks 'Upload Route'
        Uploads the route from the user selected file and shows in the cytoscape

        Args:
            contents - the file contents must be csv, xls, or ods.
            filename - the name of the file the user has uploaded

        Returns:
            processed_route - the dict with route data from the uploaded file
            processed_conditions - the dict with condition data from the uploaded file
            sustainability - the dict with sustainability data from the uploaded file
            uuid for the uploaded retrosynthesis.
        """
        if contents is not None:
            (
                processed_route,
                processed_conditions,
            ) = process_user_route_file.read_user_route_file(contents, filename)
            sustainability_data = sustainability.get_sustainability_for_all_routes(
                processed_conditions["routes"]
            )
        
            return (
                processed_route,
                processed_conditions,
                sustainability_data,
                processed_route["uuid"],
            )
        return dash.no_update

    return dash_app.server
