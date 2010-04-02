import logging
import pprint

from django.conf import settings
from django.contrib import auth
from django.contrib import messages
from django.contrib.auth.decorators import login_required, permission_required, user_passes_test
from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import PermissionDenied
from django.db.models import Count, Q
from django.forms.models import modelformset_factory
from django.http import HttpResponseRedirect, Http404
from django.shortcuts import render_to_response, get_object_or_404, redirect
from django.template import RequestContext
from django.utils.translation import ugettext as _
from django.utils.http import urlquote
from django.views.generic import list_detail, create_update

from annoying.decorators import render_to

from authority.decorators import permission_required_or_403
from authority.forms import UserPermissionForm
from authority.models import Permission

from projector.models import Project, ProjectCategory, Membership, Task, \
    Milestone, Status, Transition
from projector.forms import ProjectForm, MembershipForm, MilestoneForm, \
    StatusForm, StatusEditForm
from projector.views.task import task_create
from projector.permissions import ProjectPermission
from projector.utils.simplehg import hgrepo_detail, is_mercurial
from projector.filters import TaskFilter

from richtemplates.shortcuts import get_first_or_None

from urlparse import urljoin

def project_details(request, project_slug,
        template_name='projector/project/details.html'):
    """
    Returns selected project's detail for user given in ``request``.
    We make necessary permission checks *after* dispatching between
    normal and mercurial request, as mercurial requests has it's own
    permission requirements.
    """
    project = get_object_or_404(Project, slug=project_slug)
    if is_mercurial(request):
        return hgrepo_detail(request, project.slug)
    last_part = request.path.split('/')[-1]
    if last_part and last_part != project_slug:
        raise Http404("Not a mercurial request and path longer than should "
            "be: %s" % request.path)
    if project.is_private():
        check = ProjectPermission(user=request.user)
        if not check.view_project(project):
            raise PermissionDenied()
    context = {
        'project': project,
    }
    return render_to_response(template_name, context, RequestContext(request))

project_details.csrf_exempt = True

@render_to('projector/project/list.html')
def project_list(request):
    project_list = Project.objects.projects_for_user(user=request.user)\
        .annotate(Count('task'))
    #project_list = Project.objects.filter(membership__member=request.user)\
    #    .annotate(Count('task'))
    context = {
        'project_list' : project_list,
    }
    return context

def project_task_list(request, project_slug,
        template_name='projector/project/task_list.html'):
    project = Project.objects.get(slug=project_slug)    
    if project.is_private():
        check = ProjectPermission(request.user)
        if not check.has_perm('project_permission.view_tasks_project',
            project):
            raise PermissionDenied()

    task_list = Task.objects.filter(project__id=project.id)\
            .select_related('priority', 'status', 'author', 'project')
    filters = TaskFilter(request.GET,
        queryset=task_list, project=project)
    if request.GET and 'id' in request.GET and request.GET['id'] and filters.qs.count() == 1:
        task = filters.qs[0]
        messages.info(request, _("One task matched - redirecting..."))
        return redirect(task.get_absolute_url())
    context = {
        'project': project,
        'filters': filters,
    }
    return render_to_response(template_name, context, RequestContext(request))

@login_required
@render_to('projector/project/create.html')
def project_create(request):
    """
    New project creation view.
    """
    project = Project(
        author=request.user,
    )
    form = ProjectForm(request.POST or None, instance=project)
    if request.method == 'POST' and form.is_valid():
        project = form.save(commit=False)
        project.save()
        return HttpResponseRedirect(project.get_absolute_url())
    
    context = {
        'form' : form,
    }

    return context

@permission_required_or_403('project_permission.change_project',
    (Project, 'slug', 'project_slug'))
@render_to('projector/project/edit.html')
def project_edit(request, project_slug):
    """
    Update project view.
    """
    project = get_object_or_404(Project, slug=project_slug)
    if project.public:
        project.public = u'public'
    else:
        project.public = u'private'
    form = ProjectForm(request.POST or None, instance=project)
    if request.method == 'POST' and form.is_valid():
        project = form.save()
        message = _("Project edited successfully")
        messages.success(request, message)
        return HttpResponseRedirect(project.get_absolute_url())

    context = {
        'form' : form,
        'project': form.instance,
    }

    return context

@render_to('projector/project/milestone_list.html')
def project_milestones(request, project_slug):
    """
    Returns milestones view.
    """
    project = get_object_or_404(Project, slug=project_slug)
    if project.is_private():
        check = ProjectPermission(user=request.user)
        if not check.view_project(project):
            raise PermissionDenied()
    milestone_list = project.milestone_set\
        .annotate(Count('task'))
    context = {
        'project': project,
        'milestone_list': milestone_list,
    }
    return context

@render_to('projector/project/milestone_detail.html')
def project_milestone_detail(request, project_slug, milestone_slug):
    """
    Returns milestone detail view.
    """
    project = get_object_or_404(Project, slug=project_slug)
    milestone = get_object_or_404(Milestone, slug=milestone_slug)
    if project.is_private():
        check = ProjectPermission(user=request.user)
        if not check.view_project(project):
            raise PermissionDenied()
    context = {
        'project': project,
        'milestone': milestone,
    }
    return context

@permission_required_or_403('project_permission.change_project',
    (Project, 'slug', 'project_slug'))
@render_to('projector/project/milestone_add.html')
def project_milestones_add(request, project_slug):
    """
    Adds milestone for project.
    """
    project = get_object_or_404(Project, slug=project_slug)
    milestone = Milestone(project=project, author=request.user)
    form = MilestoneForm(request.POST or None, instance=milestone)
    if request.method == 'POST' and form.is_valid():
        milestone = form.save()
        msg = _("Milestone added successfully")
        messages.success(request, msg)
        return redirect(project.get_absolute_url())
    context = {
        'form': form,
        'project': project,
    }
    return context

@permission_required_or_403('project_permission.change_project',
    (Project, 'slug', 'project_slug'))
@render_to('projector/project/milestone_edit.html')
def project_milestone_edit(request, project_slug, milestone_slug):
    """
    Edits chosen milestone.
    """
    project = get_object_or_404(Project, slug=project_slug)
    milestone = get_object_or_404(Milestone, slug=milestone_slug)
    form = MilestoneForm(request.POST or None, instance=milestone)
    if request.method == 'POST' and form.is_valid():
        milestone = form.save()
        msg = _("Milestone updated successfully")
        messages.success(request, msg)
        return redirect(milestone.get_absolute_url())
    context = {
        'form': form,
        'project': project,
    }
    return context

@render_to('projector/project/workflow_detail.html')
def project_workflow_detail(request, project_slug):
    """
    Returns project's workflow detail view.
    """
    project = get_object_or_404(Project, slug=project_slug)
    if project.is_private():
        check = ProjectPermission(user=request.user)
        if not check.view_project(project):
            raise PermissionDenied()
    context = {
        'project': project,
    }
    return context

@permission_required_or_403('project_permission.change_project',
    (Project, 'slug', 'project_slug'))
@render_to('projector/project/workflow_edit.html')
def project_workflow_edit(request, project_slug):
    """
    Edits chosen project's workflow.
    """
    project = get_object_or_404(Project, slug=project_slug)
    StatusEditFormset = modelformset_factory(Status,
        fields=['name', 'order', 'destinations'],
        extra=0)
    formset = StatusEditFormset(request.POST or None, request.FILES or None,
        queryset=Status.objects.filter(project=project))
    if request.method == 'POST':
        if formset.is_valid():
            msg = _("Workflow updated successfully")
            messages.success(request, msg)
            for form in formset.forms:
                # update status instance
                form.instance.save()
                destinations = form.cleaned_data['destinations']
                # remove unchecked
                Transition.objects.filter(~Q(destination__in=destinations),
                    source=form.instance)\
                    .delete()
                # add new
                for destination in destinations:
                    Transition.objects.get_or_create(source=form.instance,
                        destination=destination)
            #formset.save()
    context = {
        'formset': formset,
        'project': project,
    }
    return context

@permission_required_or_403('project_permission.change_project',
    (Project, 'slug', 'project_slug'))
@render_to('projector/project/workflow_add_status.html')
def project_workflow_add_status(request, project_slug):
    """
    Adds status for project.
    """
    project = get_object_or_404(Project, slug=project_slug)
    _max_order_status = get_first_or_None(
        project.status_set.only('order').order_by('-order'))
    status = Status(project=project,
        order=_max_order_status and _max_order_status.order+1 or 1)
    form = StatusForm(request.POST or None, instance=status)
    if request.method == 'POST' and form.is_valid():
        form.save()
        msg = _("Status added successfully")
        messages.success(request, msg)
        return redirect(project.get_workflow_url())
    context = {
        'form': form,
        'project': project,
    }
    return context


@render_to('projector/project/members.html')
def project_members(request, project_slug):
    """
    Shows/updates project's members view.
    """
    project = get_object_or_404(Project, slug=project_slug)
    if project.is_private():
        check = ProjectPermission(request.user)
        if not check.has_perm('project_permission.view_members_project',
            project):
            raise PermissionDenied()
    memberships = Membership.objects\
        .filter(project=project)
    
    context = {
        'project': project,
        'memberships': memberships,
    }
    return context

@permission_required_or_403('project_permission.add_member_project',
    (Project, 'slug', 'project_slug'))
@render_to('projector/project/members_add.html')
def project_members_add(request, project_slug):
    """
    Adds member for a project.
    """
    project = get_object_or_404(Project, slug=project_slug)
    membership = Membership(
        project = project,
    )
    form = MembershipForm(request.POST or None, instance=membership)
    
    if request.method == 'POST' and form.is_valid():
        logging.info("Saving member %s for project '%s'"
            % (form.instance.member, form.instance.project))
        form.save()
        return redirect(project.get_members_url())
    elif form.errors:
        logging.error("Form contains errors:\n%s" % form.errors)

    context = {
        'project': form.instance.project,
        'form': form,
    }
    return context

@permission_required_or_403('project_permission.change_member_project',
    (Project, 'slug', 'project_slug'))
@render_to('projector/project/members_manage.html')
def project_members_manage(request, project_slug, username):
    """
    Manages membership settings and permissions of project's member.
    """
    membership = get_object_or_404(Membership,
        project__slug=project_slug, member__username=username)
    member = membership.member
    project = membership.project
    if not request.user.is_superuser and project.author == member:
        # allow if requested by superuser
        messages.warning(request, _("Project owner's membership cannot be "
            "modified. He/She has all permissions for this project."))
        return redirect(project.get_members_url())
    check = ProjectPermission(user=member)

    form = MembershipForm(request.POST or None, instance=membership)
    permissions = ProjectPermission(membership.member)
    available_permissions = [ '.'.join(('project_permission', perm))
        for perm in permissions.checks if perm.endswith('_project')]
    logging.info("Available permissions for projects are:\n%s"
        % pprint.pformat(available_permissions))
    
    # Fetch members' permissions for this project
    member_current_permissions = member\
        .granted_permissions\
        .get_for_model(project)\
        .select_related('user', 'creator', 'group', 'content_type')\
        .filter(object_id=project.id)

    def get_or_create_permisson(perm):
        for perm_obj in member_current_permissions:
            if perm_obj.codename == perm:
                return perm_obj
        perm_obj, created = Permission.objects.get_or_create(
            creator = request.user,
            content_type = ContentType.objects.get_for_model(
                membership.project),
            object_id = membership.project.id,
            codename = perm,
            user = membership.member,
            approved = False,
        )
        return perm_obj

    logging.info("Current %s's permissions:" % member)
    for perm in member_current_permissions:
        logging.info("%s | Approved is %s" % (perm, perm.approved))

    if request.method == 'POST':
        granted_perms = request.POST.getlist('perms')
        logging.debug("POST'ed perms: %s" % granted_perms)
        for perm in available_permissions:
            logging.info("Permisson %s | Member %s has it: %s"
                % (perm, member, member.has_perm(perm)))
            if perm in granted_perms and not check.has_perm(perm, project):
                # Grant perm
                logging.debug("Granting permission %s for user %s"
                    % (perm, member))
                perm_obj = get_or_create_permisson(perm)
                if not perm_obj.approved:
                    perm_obj.approved = True
                    perm_obj.save()
            if perm not in granted_perms and check.has_perm(perm, project):
                # Disable perm
                logging.debug("Disabling permission %s for user %s"
                    % (perm, member))
                perm_obj = get_or_create_permisson(perm)
                perm_obj.approved = False
                perm_obj.creator = request.user
                perm_obj.save()

    context = {
        'project': project,
        'form': form,
        'membership': membership,
        'permissions': permissions,
        'available_permissions': available_permissions,
    }
    return context

@render_to('projector/project/repository.html')
def project_browse_repository(request, project_slug, rel_repo_url):
    """
    Handles project's repository browser.
    """
    try:
        from vcbrowser import engine_from_url
        from vcbrowser.engine.base import VCBrowserError, EngineError
    except ImportError, err:
        messages.error(request, repr(err))
        messages.info(request, "vcbrowser is available at "
            "http://code.google.com/p/python-vcbrowser/")
        return {}

    project = get_object_or_404(Project, slug=project_slug)
    if project.is_private():
        check = ProjectPermission(request.user)
        if not request.user.is_authenticated() or \
            not check.read_repository_project(project):
            raise PermissionDenied()


    if not project.repository_url:
        messages.error(request, _("Repository's url is not set! Please "
            "configure project preferences first."))
        #raise Http404

    context = {
        'project': project,
    }
    
    # Some custom logic here
    revision = request.GET.get('revision', None)

    try:
        engine = engine_from_url('hg://' + project.get_repo_path())
        requested_node = engine.request(rel_repo_url, revision, fetch_content=True)
        context['root'] = requested_node
    except VCBrowserError, err:
        messages.error(request, repr(err))
    except EngineError, err:
        messages.error(request, str(err))
    return context

@render_to('projector/project/changeset_list.html')
def project_changesets(request, project_slug):
    """
    Returns repository's changesets view.
    """
    try:
        from vcbrowser import engine_from_url
        from vcbrowser.engine.base import VCBrowserError, EngineError
    except ImportError, err:
        messages.error(request, str(err))
        return {}
    project = get_object_or_404(Project, slug=project_slug)
    if project.is_private():
        check = ProjectPermission(request.user)
        if not check.read_repository_project(project):
            raise PermissionDenied()
    if not project.repository_url:
        messages.error(request, _("Repository's url is not set! Please "
            "configure project preferences first."))
    context = {
        'project': project,
    }
    try:
        engine = engine_from_url('hg://' + project.get_repo_path())
        changeset_list = [engine.get_changeset(rev) for rev in 
            reversed(engine.revision_numbers)]
        context['changeset_list'] = changeset_list
        context['engine'] = engine
    except VCBrowserError, err:
        messages.error(request, str(err))
    except EngineError, err:
        messages.error(request, str(err))
    return context
