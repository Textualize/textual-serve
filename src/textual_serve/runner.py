if __name__ == "__main__":
    import base64
    import sys
    import pickle

    if sys.__stdin__ is not None:
        app_pickle_base64 = sys.__stdin__.readline()
        app_pickle = base64.b64decode(app_pickle_base64)
        app = pickle.loads(app_pickle)
        assert hasattr(app, "run")
        app.run()
