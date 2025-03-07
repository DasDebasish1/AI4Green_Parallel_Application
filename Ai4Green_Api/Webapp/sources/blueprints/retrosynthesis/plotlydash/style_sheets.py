class WebElementsStyles(object):

    DATATABLE_STYLE = {
        "max-width": "2rem",
        'whiteSpace': 'normal',
        'height': 'auto',
        'margin': '0.5rem'
    }

    SIDEBAR_STYLE = {
        "position": "inline-block",
        "top": 0,
        "left": 0,
        "bottom": 0,
        # "width": "28rem",
        "min-height": "100vh",
        "height": "100%",
        # "margin": 0,
        # "z-index": 1,
        "overflow-x": "hidden",
        # "transition": "all 0.5s",
        "padding": "0.5rem",
        "padding-bottom": "1rem",
        # "background-color": "#f8f9fa",
        'box - sizing': 'border - box',
        # "flex-wrap": "wrap"
    }

    SIDEBAR_HIDDEN = {
        "position": "fixed",
        "top": 62.5,
        "left": "-16rem",
        "bottom": 0,
        "width": "16rem",
        "height": "100%",
        "z-index": 1,
        "overflow-x": "hidden",
        "transition": "all 0.5s",
        "padding": "0rem 0rem",
        "background-color": "#f8f9fa",
    }
    RETRO_TREE_STYLE = {
        "position": "inline-block"

    }

    CONTENT_STYLE = {
        "overflow-x": "clip",
        #"height": "auto"
    }

    # LOADING_STYLE = {
    #     # loading:after{
    #     'content': 'Loading text',
    #     # 'display': 'block',
    #     'color': 'red'
    #
    #     # 'position': 'absolute',
    #     # 'top': '50 %',
    #     # 'left': '50 %',
    #     # 'transform': 'translate(-50 %, -50 %)'
    # }


class CytoscapeStyles(object):
    basic_stylesheet = [
        {'selector': 'node',
         'style': {
             'shape': 'rectangle',
             # 'border-width': 2,  # no border that would increase node size
             'background-width': '100%',
             'background-height': '100%',
             'height': '100%',
             'width': '100%',
             # 'border-style': 'solid',
         }
         },
        {'selector': 'node[label]',
         'style': {
             'content': 'data(label)',
             'color': 'black',
         }},
        {'selector': ':selected',
         'style': {
             'border-color': 'Orange',
             'border-width': '5',
             'shape': 'square',

             'background-color': 'SteelBlue',
             'line-color': 'black',
             'target-arrow-color': 'black',
             'source-arrow-color': 'black'
         }
         }
    ]

    node_border_dict = {"terminal": {"colour": "#198754", "style": "solid", "width": "5"},  # lawn green
                        "target": {"colour": "black", "style": "solid", "width": "5"},
                        "normal": {"colour": "black", "style": "dashed", "width": "1"}
                        }

    scale_factor = 1
