import logging

from django.conf import settings
from django.core.exceptions import PermissionDenied


from projector.contrib.git.utils import is_git_request
from projector.contrib.git.githttp import GitWebServer
from projector.views.project import ProjectView

from vcs.web.simplevcs.utils import log_error, ask_basic_auth, basic_auth
from vcs.web.simplevcs.signals import pre_clone, post_clone, pre_push, post_push


class ProjectGitBaseView(ProjectView):
    """
    Base view class for git http handler.

    Extra attributes:

    - ``type``: returns ``READ`` or ``WRITE`` value of ``Type`` subclass of
      ``projector.contrib.git.githttp.GitWebServer``. It specifies if user
      is reading from or writing into the repository.

    Signals:

    Basing on ``type`` attribute, git handler sends one of ``pre_clone``,
    ``post_clone``, ``pre_push`` or ``post_push`` signal from
    ``vcs.web.simplevcs.signals``.
    """

    csrf_exempt = True

    def __init__(self, *args, **kwargs):
        obj = super(ProjectGitBaseView, self).__init__(*args, **kwargs)
        self.mimetype = 'text/plain'
        self.charset = settings.DEFAULT_CHARSET
        self.headers = {}
        return obj

    def __before__(self):
        if not is_git_request(self.request):
            logging.debug("Not a GIT request")
            #raise Http404
        logging.info("Git request\n%s %s" % (
            self.request.META['REQUEST_METHOD'], self.request.META['PATH_INFO']))
        logging.debug("Catched git request by %s view" % self.__class__.__name__)
        logging.debug("Path is: %s" % self.request.META['PATH_INFO'])
        logging.debug("Query is: %s" % self.request.META['QUERY_STRING'])

    def get_required_perms(self):
        if is_git_request(self.request):
            # Let undelying code verify permissions
            return []
        return super(ProjectGitBaseView, self).get_required_perms()


class ProjectGitHandler(ProjectGitBaseView):

    def response(self, request, username, project_slug):
        try:
            if 'git-upload-pack' in self.request.META['PATH_INFO']:
                self.type = GitWebServer.Type.READ
                pre_push.send(sender=self,
                    repo_path=self.project.repository.path,
                    ip=self.request.META.get('REMOTE_ADDR', ''),
                    username=self.request.user.username)
            elif 'git-receive-pack' in self.request.META['PATH_INFO']:
                self.type = GitWebServer.Type.WRITE
                pre_clone.send(sender=self,
                    repo_path=self.project.repository.path,
                    ip=self.request.META.get('REMOTE_ADDR', ''),
                    username=self.request.user.username)
            else:
                self.type = GitWebServer.Type.UNSPECIFIED

            auth_response = self.get_authed_user()
            if auth_response:
                return auth_response
            git_server = GitWebServer(self.project.repository)
            response = git_server.get_response(request)
            if self.is_read():
                post_clone.send(sender=self,
                    repo_path=self.project.repository.path,
                    ip=self.request.META.get('REMOTE_ADDR', ''),
                    username=self.request.user.username)
            elif self.is_write():
                post_push.send(sender=self,
                    repo_path=self.project.repository.path,
                    ip=self.request.META.get('REMOTE_ADDR', ''),
                    username=self.request.user.username)
        except Exception, err:
            log_error(err)
            raise err

        #print response
        return response

    def get_authed_user(self):
        if self.project.is_public():
            return None
        # Check if user have been already authorized or ask to
        self.request.user = basic_auth(self.request)
        if self.request.user is None:
            return ask_basic_auth(self.request,
                realm=self.project.config.basic_realm)
        raise PermissionDenied

    def is_read(self):
        return self.type == GitWebServer.Type.READ

    def is_write(self):
        return self.type == GitWebServer.Type.WRITE

