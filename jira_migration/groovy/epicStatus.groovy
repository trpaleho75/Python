import com.onresolve.scriptrunner.runner.rest.common.CustomEndpointDelegate
import groovy.json.JsonBuilder
import groovy.json.JsonSlurper
import javax.ws.rs.core.Response
import groovy.transform.BaseScript
import javax.ws.rs.core.MultivaluedMap
import com.atlassian.jira.component.ComponentAccessor
import com.atlassian.jira.issue.fields.CustomField
import com.atlassian.jira.bc.issue.search.SearchService
import com.atlassian.jira.issue.search.SearchException
import com.atlassian.jira.web.bean.PagerFilter

@BaseScript CustomEndpointDelegate delegate

def getEpicStatuses(String body) {
    // Get post data
    def slurper = new groovy.json.JsonSlurper()
	def root = slurper.parseText(body)
    
    // Get field
    def field = ComponentAccessor.customFieldManager.getCustomFieldObjectsByName("Epic Status")[0]

    // Get user
    def user = ComponentAccessor.userManager.getUserByName(root.username)

    // Get an Epic
    final jqlQuery = "issuetype = Epic"
    def searchService = ComponentAccessor.getComponentOfType(SearchService)
    def parseResult = searchService.parseQuery(user, jqlQuery)
    def issues = null
    if (!parseResult.valid) {
        log.error('Invalid query')
        return null
    }

    try {
        // Perform the query to get the issues
        def pagerFilter = new PagerFilter(1)
        def results = searchService.search(user, parseResult.query, pagerFilter)
        issues = results.results

    } catch (SearchException e) {
        e.printStackTrace()
        null
    }

    // Get options
    def validOptions = ComponentAccessor.optionsManager.getOptions(field.getRelevantConfig(issues[0]))
    def optionList = []
    validOptions.each { option ->
        optionList.add("\"${option}\"")
    }
    return optionList
}

// Rest Endpoint
getEpicStatusOptions(httpMethod: "POST", groups: ["SDTEOB_ENVIRONMENT_ADMINS", "monarch_environment_admins"]) {
    MultivaluedMap queryParams, String body ->
	def builder = new groovy.json.JsonBuilder()
    def response = getEpicStatuses(body)
    def responseJson = builder(response)
    return Response.ok(responseJson.toString()).build()
}