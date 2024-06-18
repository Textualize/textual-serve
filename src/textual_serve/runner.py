if __name__ == "__main__":
    print("RUNNER")
    import base64
    import sys
    import pickle

    if sys.__stdin__ is not None:
        print(1)
        app_pickle_base64 = sys.__stdin__.readline()
        print(2)
        app_pickle = base64.b64decode(app_pickle_base64)
        print(3, app_pickle)
        try:
            app = pickle.loads(app_pickle)
        except Exception as error:
            print(error)
            raise

        print(4)
        print("RUNNER", app)
        assert hasattr(app, "run")
        app.run()
