from django import forms
from django.http import HttpRequest
from django.utils.translation import ugettext as _

from projector.core.exceptions import ProjectorError

class BaseExternalForkForm(forms.Form):
    """
    Base form class for all forms used to create *external* fork.
    """

    help_text = ''

    as_private = forms.BooleanField(initial=False, label=_('As private'),
        help_text=_('Forks project as your private project'), required=False)

    def __init__(self, request, *args, **kwargs):
        """
        Needs one extra parameter to be passed:

        :param request: :py:class:`django.http.HttpRequest`` object is required
          at forking process and/or validation of the form
        """
        if not isinstance(request, HttpRequest):
            raise ValueError("Fork form's first argument should always be a "
                             "request")
        form = super(BaseExternalForkForm, self).__init__(*args, **kwargs)
        self.request = request
        return form

    def is_public(self):
        if not hasattr(self, 'cleaned_data'):
            raise ProjectorError("Must be called after form is validated")
        return not self.cleaned_data['as_private']

    def is_private(self):
        return not self.is_public()

    def get_url(self):
        """
        Should return url to be set as ``fork_url`` attribute of the
        ``Project`` model.
        """
        raise NotImplementedError("Must be implemented in order to let project "
            "instance know where it was forked from")

    def fork(self):
        """
        Actions needed to fork the project. Real fork command should be fired by
        ``Project``'s ``post_save`` signal handler.

        This method should raise only subclass of type:
        ``projector.core.exceptions.ProjectorError``.  That way all errors
        would be returned to the user if he/she would try to fork project from
        external location and process fails. It's not validation error - form
        may validate properly. This errors should be raised while trying to
        fork from external location. We can get various errors here, such as
        problem with network etc..

        """
        raise NotImplementedError("ForkForm requires ``fork`` method to "
            "implements logic required for the forking process")

