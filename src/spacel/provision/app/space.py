import logging

from spacel.provision.cloudformation import BaseCloudFormationFactory

logger = logging.getLogger('spacel')


class SpaceElevatorAppFactory(BaseCloudFormationFactory):
    def __init__(self, clients, change_sets, uploader, app_template):
        super(SpaceElevatorAppFactory, self).__init__(clients, change_sets,
                                                      uploader)
        self._app_template = app_template

    def app(self, app):
        """
        Provision an app in all regions.
        :param app:  App to provision.
        :returns True if updates completed.
        """
        app_name = app.full_name
        updates = {}
        for region in app.regions:
            template, secret_params = self._app_template.app(app, region)
            if not template and not secret_params:
                logger.warn('App %s will not be updated, invalid syntax!',
                            app_name)
                continue
            updates[region] = self._stack(app_name, region, template,
                                          secret_parameters=secret_params)
        return self._wait_for_updates(app_name, updates)

    def delete_app(self, app):
        """
        Delete an app in all regions.
        :param app:  App to delete.
        """
        app_name = app.full_name
        updates = {}
        for region in app.regions:
            updates[region] = self._delete_stack(app_name, region)
        self._wait_for_updates(app_name, updates)
